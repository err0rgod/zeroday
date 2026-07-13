import zipfile
import os

def create_zip():
    print("Building lambda_deploy.zip...")
    with zipfile.ZipFile('lambda_deploy.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add lib and web directories
        for folder in ['lib', 'web']:
            if os.path.exists(folder):
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        filepath = os.path.join(root, file)
                        # Exclude cache and unwanted files
                        if '__pycache__' not in filepath and not filepath.endswith('.db'):
                            arcname = filepath.replace('\\', '/')
                            zf.write(filepath, arcname)
        
        # Add handler.py to root
        if os.path.exists('handler.py'):
            zf.write('handler.py', 'handler.py')
        
        # Add temp_linux_libs contents to root of zip
        if os.path.exists('temp_linux_libs'):
            for root, dirs, files in os.walk('temp_linux_libs'):
                for file in files:
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, 'temp_linux_libs').replace('\\', '/')
                    zf.write(filepath, arcname)
    print("Zip created successfully.")

if __name__ == '__main__':
    create_zip()
