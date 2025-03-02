import os
import csv
import io
import shutil
import time
import random
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.auth.transport.requests import Request

# --- Configuration ---
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'
CSV_FILE = 'files_to_migrate.csv'  # Default CSV file name
SOURCE_FOLDER_ID = 'your_source_folder_id'
BACKUP_FOLDER_NAME = 'bak'
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.metadata'
]
MAX_RETRIES = 5
INITIAL_BACKOFF = 1

# --- Helper Functions ---

def retry_with_backoff(func):
    """Decorator for retrying a function with exponential backoff."""
    def wrapper(*args, **kwargs):
        retries = 0
        backoff = INITIAL_BACKOFF
        while retries < MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except HttpError as error:
                if error.resp.status in [429, 500, 502, 503, 504]:
                    retries += 1
                    wait_time = backoff * (2 ** retries) + random.uniform(0, 1)
                    print(f"  Retrying in {wait_time:.2f} seconds (attempt {retries} of {MAX_RETRIES})...")
                    time.sleep(wait_time)
                else:
                    raise
            except (OSError, IOError) as error:
                 retries += 1
                 wait_time = backoff * (2**retries) + random.uniform(0,1)
                 print(f" Network error. Retrying in {wait_time:.2f} seconds")
                 time.sleep(wait_time)

        raise Exception(f"Max retries ({MAX_RETRIES}) exceeded for {func.__name__}.")
    return wrapper

def get_drive_service():
    """Authenticates and returns a Google Drive API service object using OAuth 2.0."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    service = build('drive', 'v3', credentials=creds)
    return service

@retry_with_backoff
def get_file_metadata(service, file_id, fields='name, id, mimeType, owners, parents'):
    """Retrieves metadata for a file."""
    try:
        file = service.files().get(fileId=file_id, fields=fields, supportsAllDrives=True).execute()
        return file
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

@retry_with_backoff
def create_folder(service, folder_name, parent_id=None):
    """Creates a folder in Google Drive."""
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        file_metadata['parents'] = [parent_id]

    try:
        folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
        print(f'Folder created: {folder_name} ({folder.get("id")})')
        return folder.get('id')
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

@retry_with_backoff
def copy_file(service, file_id, new_file_name=None):
    """Copies a file."""
    try:
        original_file = get_file_metadata(service, file_id)
        if not original_file:
            print(f"  Could not retrieve metadata for file ID: {file_id}")
            return None

        file_metadata = {
            'name': new_file_name or original_file['name'],
        }

        copied_file = service.files().copy(
            fileId=file_id,
            body=file_metadata,
            fields='id, name, parents',
            supportsAllDrives=True
        ).execute()

        print(f'  File copied: {original_file["name"]} -> {copied_file.get("name")} ({copied_file.get("id")})')
        return copied_file.get('id')

    except HttpError as error:
        print(f'  An error occurred while copying {file_id}: {error}')
        return None

@retry_with_backoff
def move_file(service, file_id, new_parent_id):
    """Moves a file to a new folder."""
    try:
        file = service.files().get(fileId=file_id, fields='parents', supportsAllDrives=True).execute()
        previous_parents = ",".join(file.get('parents'))
        file = service.files().update(fileId=file_id,
                                      addParents=new_parent_id,
                                      removeParents=previous_parents,
                                      fields='id, parents',
                                      supportsAllDrives=True).execute()
        print(f'  File moved: {file_id} to {new_parent_id}')
        return file.get('id')
    except HttpError as error:
        print(f'  An error occurred: {error}')
        return None

@retry_with_backoff
def download_and_upload_file(service, file_id, original_filename):
    """Downloads/re-uploads a file (used as fallback)."""
    original_file = get_file_metadata(service, file_id)
    if not original_file:
        print(f"  Could not retrieve metadata for file ID: {file_id}")
        return None

    mime_type = original_file.get('mimeType')
    if mime_type == 'application/vnd.google-apps.document':
        export_mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        file_extension = '.docx'
    elif mime_type == 'application/vnd.google-apps.spreadsheet':
        export_mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        file_extension = '.xlsx'
    elif mime_type == 'application/vnd.google-apps.presentation':
        export_mime = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        file_extension = '.pptx'
    else:
        export_mime = None
        file_extension = os.path.splitext(original_filename)[1]

    try:
        if export_mime:
            request = service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = service.files().get_media(fileId=file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"  Download {int(status.progress() * 100)}%.")

        fh.seek(0)

        new_file_name = os.path.splitext(original_filename)[0] + file_extension
        file_metadata = {
            'name': new_file_name,
        }

        if export_mime:
             media = MediaIoBaseUpload(fh, mimetype=export_mime, resumable=True)
        else:
             media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True)

        new_file = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
        print(f'  File downloaded and re-uploaded: {new_file_name} ({new_file.get("id")})')
        return new_file.get('id')

    except HttpError as error:
        print(f'  An error occurred: {error}')
        return None

    finally:
        if 'fh' in locals():
           fh.close()

@retry_with_backoff
def list_files_in_folder(service, folder_id):
    """Lists files in a folder with retries, handling pagination."""
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="nextPageToken, files(id, name, mimeType, owners)",
        supportsAllDrives=True
    ).execute()
    return results
def process_item(service, file_id, backup_folder_id):
    """Processes a single file or folder (recursively)."""
    file_metadata = get_file_metadata(service, file_id)
    if not file_metadata:
        print(f"  Skipping - Could not retrieve metadata for file ID: {file_id}")
        return

    if file_metadata['mimeType'] == 'application/vnd.google-apps.folder':
        print(f"  Processing folder: {file_metadata['name']} ({file_id})")
        new_folder_id = create_folder(service, file_metadata['name'], parent_id=backup_folder_id)
        if not new_folder_id:
            print(f"    Error creating subfolder in backup folder.")
            return

        try:
            results = list_files_in_folder(service, file_id) #now uses retry
            items = results.get('files', [])

            #handle pagination
            while 'nextPageToken' in results:
                results = list_files_in_folder(service, file_id, results['nextPageToken'])
                items.extend(results.get('files',[]))
        except HttpError as error:
                print(f"    An error occurred listing folder contents: {error}")
                return

        for item in items:
            process_item(service, item['id'], new_folder_id)

        move_file(service, file_id, backup_folder_id)

    else:
        print(f"  Processing file: {file_metadata['name']} ({file_id})")
        copied_file_id = copy_file(service, file_id)
        if not copied_file_id:
            print(f"    Copy failed, attempting download/upload...")
            file_name = file_metadata['name']
            copied_file_id = download_and_upload_file(service, file_id, file_name)

        if not copied_file_id:
            print(f"    Failed to copy file ID: {file_id}")
            return

        move_file(service, file_id, backup_folder_id)

def process_csv(service, csv_file, backup_folder_id):
    """Processes the CSV."""
    try:
        with open(csv_file, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader, None)

            for row in reader:
                if not row or len(row) <= 1:
                    continue

                url = row[1].strip()
                file_id = None
                if "drive.google.com/file/d/" in url:
                    file_id = url.split("drive.google.com/file/d/")[1].split("/")[0]
                elif "drive.google.com/drive/folders/" in url:
                    file_id = url.split("drive.google.com/drive/folders/")[1].split("?")[0]

                if not file_id:
                    print(f"Skipping row - Could not extract File ID from URL: {url}")
                    continue

                print(f"Processing file ID: {file_id}, URL: {url}")
                process_item(service, file_id, backup_folder_id)

    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def main():
    """Main function."""
    service = get_drive_service()
    if not service:
        print("Failed to initialize Drive service.")
        return

    backup_folder_id = None
    try:
        q = f"mimeType = 'application/vnd.google-apps.folder' and name = '{BACKUP_FOLDER_NAME}' and 'root' in parents and trashed = false"
        response = service.files().list(q=q, fields='files(id, name)',supportsAllDrives = True).execute()
        folders = response.get('files', [])

        if folders:
            backup_folder_id = folders[0]['id']
            print(f"Backup folder '{BACKUP_FOLDER_NAME}' already exists with ID: {backup_folder_id}")
        else:
            backup_folder_id = create_folder(service, BACKUP_FOLDER_NAME)
            if not backup_folder_id:
                print("Error: Could not create backup folder.")
                return
    except HttpError as error:
        print(f"Error checking/creating backup folder: {error}")
        return

    process_csv(service, CSV_FILE, backup_folder_id)
    print("Script finished.")

if __name__ == '__main__':
     main()
