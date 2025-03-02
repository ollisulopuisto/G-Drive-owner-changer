# Google Drive Migration Script

This script helps you migrate files in Google Drive by copying files owned by other users and moving the originals to a backup folder. This allows you to move a parent folder even if you don't own all the files within it. The script uses the Google Drive API v3 and OAuth 2.0 for authentication.

## Features

*   **Copies files:** Creates copies of files owned by other users.
*   **Moves originals:** Moves the original files to a specified backup folder.
*   **Handles folders recursively:**  Processes subfolders and their contents.
*   **Handles Google Docs, Sheets, and Slides:**  Correctly exports and re-uploads Google Workspace documents.
*   **Robust error handling:** Includes exponential backoff and retries for resilience to network issues and API rate limits.
*   **OAuth 2.0 Authentication:** Uses your Google account credentials for secure access, avoiding the need for service accounts and domain-wide delegation.

## Prerequisites

*   A Google account.
*   Python 3.7+ installed.
*   A Google Cloud project with the Google Drive API enabled.
*   OAuth 2.0 credentials for a "Desktop app" configured in your Google Cloud project.

## Setup

1.  **Create a Google Cloud Project:**
    *   Go to the Google Cloud Console: [https://console.cloud.google.com/](https://console.cloud.google.com/)
    *   Create a new project or select an existing one.

2.  **Enable the Google Drive API:**
    *   In the Cloud Console, search for "Google Drive API" and enable it for your project.

3.  **Create OAuth 2.0 Credentials:**
    *   Go to "APIs & Services" -> "Credentials".
    *   Click "+ CREATE CREDENTIALS" -> "OAuth client ID".
    *   Choose "Desktop app" as the application type.
    *   Give it a name (e.g., "Drive Migration Script").
    *   Click "CREATE".
    *   Download the JSON file and save it as `credentials.json` in the same directory as the script.

4.  **Install Dependencies:**

    ```bash
    pip install -r requirements.txt
    ```
    This command uses the `requirements.txt` file (see below) to install all necessary packages.  It is best practice to do this within a Python virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On macOS/Linux
    .venv\Scripts\activate  # On Windows
    pip install -r requirements.txt
    ```

5.  **Configure the Script:**
    *   Rename the downloaded OAuth credentials file to `credentials.json` and place it in the same directory as `migrate_drive_files.py`.
    *   Edit `migrate_drive_files.py`:
        *   Set `CSV_FILE` to the *name* of your CSV file (e.g., `'my_files.csv'`).  You can leave the default `'files_to_migrate.csv'` if you prefer.
        *   Set `SOURCE_FOLDER_ID` to the ID of the *parent* folder you want to move. You can find the folder ID in the URL when you open the folder in Google Drive (e.g., `https://drive.google.com/drive/folders/YOUR_FOLDER_ID`).
        *   (Optional) Change `BACKUP_FOLDER_NAME` if you want a different name for the backup folder.

## Usage

1.  **Prepare the CSV File:**
    *   In Google Drive, select the *parent* folder you want to move.
    *   Click the three dots (More actions) menu and choose "Download".
    *   Google Drive will prepare a ZIP file.  If there are files you don't own, you'll be prompted to download a CSV file listing those files. Download this CSV file.
    *  Save the downloaded CSV file, with the name you configured in `CSV_FILE` (default is `files_to_migrate.csv`) in the same directory as the script.

2.  **Run the Script:**

    ```bash
    python migrate_drive_files.py
    ```

    *   The first time you run the script, it will open a browser window and ask you to log in to your Google account and grant permissions.  This is the OAuth 2.0 authentication process.  Your credentials will be saved to `token.json` so you won't have to re-authorize every time.
    *  The script will:
        1. Create a top level "bak" folder if one doesn't exist
        2. Copy all "unmovable" files
        3. Move the original "unmovable" files and folders into the "bak" folder

3.  **Move the Parent Folder (Manually):**  After the script finishes, you can now move the original parent folder in the Google Drive web interface.

4. **Troubleshooting**
     * **`FileNotFoundError`**: If the script cannot locate a file, and you have run it more than once, it may be that the file or containing folder has been moved to the `bak/` folder.
     * **`An error occurred: <HttpError 429`**: If the script encounters a rate-limiting error, the `retry_with_backoff` decorator will automatically add wait time, and retry the call.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
