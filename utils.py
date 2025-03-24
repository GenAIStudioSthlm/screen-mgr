import os
def delete_file(file_path: str):

      # Check if file exists
    if os.path.exists(file_path):
        try:
            # Delete the file
            os.remove(file_path)
            print(f"Deleted file: {file_path}")
        except Exception as e:
            print(f"Error deleting file: {e}")
            return {"error": f"Failed to delete file: {str(e)}"}
    else:
        print(f"File not found: {file_path}")
        return {"error": "File not found"}

    return {"message": "File deleted successfully."}