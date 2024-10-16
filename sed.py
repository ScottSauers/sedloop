import subprocess
import shutil
import os
import tempfile
import pyperclip
from pyperclip import PyperclipException

def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def parse_cargo_output(output):
    errors = 0
    warnings = 0
    error_block = False
    
    for line in output.splitlines():
        if "error:" in line:
            errors += 1
        elif "warnings emitted" in line:
            warnings += int(line.split()[0])
        elif "warnings" in line and "emitted" not in line:
            warnings += 1
        elif "could not compile" in line:
            errors += 1
        elif "due to" in line and "errors" in line:
            error_count = int(line.split()[2])
            errors += error_count

    return errors, warnings


# Function to run cargo check and cargo test, then return error and warning counts for both
def run_cargo_checks():
    _, check_output, _ = run_command("cargo check")
    check_errors, check_warnings = parse_cargo_output(check_output)

    _, test_output, _ = run_command("cargo test")
    test_errors, test_warnings = parse_cargo_output(test_output)

    return check_errors, check_warnings, test_errors, test_warnings

# Main function to process sed commands
def process_sed_commands():
    try:
        # Try to get content from the clipboard
        clipboard_content = pyperclip.paste().strip()

        if clipboard_content.startswith("sed"):
            sed_commands = [clipboard_content]
            print(f"Using sed command from clipboard: {clipboard_content}")
        else:
            raise PyperclipException  # Fallback to file if clipboard content is not a sed command
    except PyperclipException:
        print("Clipboard unavailable or doesn't contain a sed command. Checking sed.sh file instead.")
        sed_file = 'sed.sh'
        if not os.path.exists(sed_file):
            print(f"{sed_file} not found in the current directory.")
            return

        with open(sed_file, 'r') as file:
            sed_commands = [line.strip() for line in file.readlines() if line.strip()]

    # Initial cargo check and test to get baseline errors and warnings
    print("Running initial cargo check and test...")
    initial_check_errors, initial_check_warnings, initial_test_errors, initial_test_warnings = run_cargo_checks()

    print(f"Initial check errors: {initial_check_errors}, Initial check warnings: {initial_check_warnings}")
    print(f"Initial test errors: {initial_test_errors}, Initial test warnings: {initial_test_warnings}")

    # Temporary directory to store backups
    with tempfile.TemporaryDirectory() as tmpdirname:
        for sed_command in sed_commands:
            print(f"\nProcessing command: {sed_command}")

            # Backup files before applying sed (skip if no files are targeted)
            target_files = []  # We will extract target files based on the sed command
            try:
                parts = sed_command.split()
                for part in parts:
                    if os.path.exists(part):
                        target_files.append(part)

                if not target_files:
                    print(f"No valid files found in command: {sed_command}, skipping.")
                    continue

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

                # Run cargo check and test again
                new_check_errors, new_check_warnings, new_test_errors, new_test_warnings = run_cargo_checks()

                # Determine error and warning differences
                check_error_diff = initial_check_errors - new_check_errors
                check_warning_diff = initial_check_warnings - new_check_warnings
                test_error_diff = initial_test_errors - new_test_errors
                test_warning_diff = initial_test_warnings - new_test_warnings

                print(f"New check errors: {new_check_errors}, New check warnings: {new_check_warnings}")
                print(f"New test errors: {new_test_errors}, New test warnings: {new_test_warnings}")

                # Check the conditions for applying the change
                if ((new_check_errors <= initial_check_errors and new_test_errors <= initial_test_errors) and 
                    (new_check_errors < initial_check_errors or new_test_errors < initial_test_errors or
                     new_check_warnings < initial_check_warnings or new_test_warnings < initial_test_warnings)):

                    # Check if the reduction in errors is suspiciously large
                    if (check_error_diff > 8 and check_error_diff > initial_check_errors / 2) or \
                       (test_error_diff > 8 and test_error_diff > initial_test_errors / 2):
                        print(f"Warning: Unusual error reduction detected, skipping this sed.")
                        # Restore from backup
                        for target_file, backup_file in backups.items():
                            shutil.copy(backup_file, target_file)
                    else:
                        # Apply the change for real (already applied in tentative phase)
                        print("Change improves code or reduces warnings, applying the change for real.")
                        initial_check_errors, initial_check_warnings = new_check_errors, new_check_warnings
                        initial_test_errors, initial_test_warnings = new_test_errors, new_test_warnings
                else:
                    # Revert to the original files if no improvement or if errors increased
                    print("No improvement detected or errors increased, reverting the change.")
                    for target_file, backup_file in backups.items():
                        shutil.copy(backup_file, target_file)

            except Exception as e:
                print(f"Error processing sed command '{sed_command}': {e}")
                continue

if __name__ == "__main__":
    process_sed_commands()
