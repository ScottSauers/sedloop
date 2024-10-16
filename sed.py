import subprocess
import shutil
import os
import tempfile

# Function to run a command and capture the output
def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

# Function to parse the output of cargo check for errors and warnings
def parse_cargo_output(output):
    errors = 0
    warnings = 0
    for line in output.splitlines():
        if "error:" in line:
            errors += 1
        elif "warning:" in line:
            warnings += 1
    return errors, warnings

# Main function to process sed commands
def process_sed_commands():
    sed_file = 'sed.sh'
    if not os.path.exists(sed_file):
        print(f"{sed_file} not found in the current directory.")
        return

    # Read the sed.sh file
    with open(sed_file, 'r') as file:
        sed_commands = file.readlines()

    # Initial cargo check to get baseline errors and warnings
    print("Running initial cargo check...")
    _, initial_output, _ = run_command("cargo check")
    initial_errors, initial_warnings = parse_cargo_output(initial_output)

    print(f"Initial errors: {initial_errors}, Initial warnings: {initial_warnings}")

    # Temporary directory to store backups
    with tempfile.TemporaryDirectory() as tmpdirname:
        for sed_command in sed_commands:
            sed_command = sed_command.strip()
            if not sed_command:
                continue

            print(f"\nProcessing command: {sed_command}")

            # Backup files before applying sed (skip if no files are targeted)
            target_files = []  # We will extract target files based on the sed command
            try:
                parts = sed_command.split()
                for part in parts:
                    if os.path.exists(part):  # If it’s a valid file path
                        target_files.append(part)

                if not target_files:
                    print(f"No valid files found in command: {sed_command}, skipping.")
                    continue

                # Back up target files
                backups = {}
                for target_file in target_files:
                    backup_path = os.path.join(tmpdirname, os.path.basename(target_file))
                    shutil.copy(target_file, backup_path)
                    backups[target_file] = backup_path

                # Apply the sed command (tentative)
                retcode, _, stderr = run_command(sed_command)
                if retcode != 0:
                    print(f"Failed to run command: {sed_command}, skipping.")
                    continue

                # Run cargo check again
                _, new_output, _ = run_command("cargo check")
                new_errors, new_warnings = parse_cargo_output(new_output)

                # Determine whether to apply the change
                error_diff = initial_errors - new_errors
                warning_diff = initial_warnings - new_warnings

                print(f"New errors: {new_errors}, New warnings: {new_warnings}")
                print(f"Error diff: {error_diff}, Warning diff: {warning_diff}")

                if new_errors < initial_errors or (new_errors == initial_errors and new_warnings < initial_warnings):
                    # Check if the reduction in errors is suspiciously large
                    if error_diff > 8 and error_diff > initial_errors / 2:
                        print(f"Warning: Unusual error reduction detected ({error_diff} errors). Skipping this sed.")
                        # Restore from backup
                        for target_file, backup_file in backups.items():
                            shutil.copy(backup_file, target_file)
                    else:
                        # Apply the change for real (already applied in tentative phase)
                        print("Change improves code or reduces warnings, applying the change for real.")
                        initial_errors, initial_warnings = new_errors, new_warnings
                else:
                    # Revert to the original files if no improvement
                    print("No improvement detected, reverting the change.")
                    for target_file, backup_file in backups.items():
                        shutil.copy(backup_file, target_file)

            except Exception as e:
                print(f"Error processing sed command '{sed_command}': {e}")
                continue

if __name__ == "__main__":
    process_sed_commands()
