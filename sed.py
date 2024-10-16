import subprocess
import shutil
import os
import tempfile
import pyperclip
from pyperclip import PyperclipException
import re

def run_command(command):
    """
    Executes a shell command and captures its output.
    """
    result = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    return result.returncode, result.stdout

def parse_cargo_output(output):
    """
    Parses the output from cargo commands to count errors and warnings.
    """
    errors = 0
    warnings = 0

    # Regex to catch error and warning summaries
    compile_fail_pattern = re.compile(
        r'^error:\s+could not compile `.*?`.*?due to\s+(\d+)\s+previous error[s]?;?\s+(\d+)\s+warnings? emitted',
        re.IGNORECASE
    )
    individual_error_pattern = re.compile(r'^\s*error:\s+(?!\[E)')
    individual_warning_pattern = re.compile(r'^\s*warning:\s+(?!\[E)')

    for line in output.splitlines():
        compile_fail_match = compile_fail_pattern.match(line)
        if compile_fail_match:
            error_count = int(compile_fail_match.group(1))
            warning_count = int(compile_fail_match.group(2))
            errors += error_count
            warnings += warning_count
            continue

        if individual_error_pattern.search(line):
            errors += 1

        if individual_warning_pattern.search(line):
            warnings += 1

    return errors, warnings

def run_cargo_checks():
    """
    Runs 'cargo check' and 'cargo test', parsing their outputs.
    """
    _, check_output = run_command("cargo check")
    check_errors, check_warnings = parse_cargo_output(check_output)

    _, test_output = run_command("cargo test")
    test_errors, test_warnings = parse_cargo_output(test_output)

    return check_errors, check_warnings, test_errors, test_warnings

def backup_rs_files(source_dir, backup_dir):
    """
    Backs up all .rs files in any subdir of source_dir to backup_dir while remembering their locations.
    """
    file_mapping = {}

    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".rs"):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, source_dir)
                backup_path = os.path.join(backup_dir, relative_path)
                
                # Create directories in the backup path if they don't exist
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)

                # Copy the .rs file to the backup directory
                shutil.copy(full_path, backup_path)

                # Store the original location in the mapping
                file_mapping[backup_path] = full_path

    print(f"Backup of all .rs files created in '{backup_dir}'")
    return file_mapping

def restore_rs_files(file_mapping):
    """
    Restores the .rs files from their backup locations to their original locations.
    """
    for backup_path, original_path in file_mapping.items():
        shutil.copy(backup_path, original_path)
    print("Restored all .rs files from backup.")

def process_sed_commands():
    """
    Processes sed commands, applying only if they don't increase the number of errors.
    Uses an initial backup of .rs files to restore if errors increase.
    """
    # Determine the current working directory
    source_dir = os.getcwd()

    # Create a temporary directory for the initial backup of .rs files
    initial_backup_dir = tempfile.mkdtemp(prefix="initial_backup_")
    file_mapping = backup_rs_files(source_dir, initial_backup_dir)

    try:
        # Attempt to get sed commands from the clipboard
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
            shutil.rmtree(initial_backup_dir)  # Clean up the initial backup before exiting
            return

        with open(sed_file, 'r') as file:
            sed_commands = [line.strip() for line in file.readlines() if line.strip()]

    # Initial cargo check and test to get baseline errors and warnings
    print("Running initial cargo check and test...")
    initial_check_errors, initial_check_warnings, initial_test_errors, initial_test_warnings = run_cargo_checks()

    print(f"Initial check errors: {initial_check_errors}, Initial check warnings: {initial_check_warnings}")
    print(f"Initial test errors: {initial_test_errors}, Initial test warnings: {initial_test_warnings}")

    # Store the initial number of errors to ensure they don't increase overall
    initial_total_errors = initial_check_errors + initial_test_errors

    # Temporary directory to store per-command backups
    with tempfile.TemporaryDirectory() as tmpdirname:
        for idx, sed_command in enumerate(sed_commands, start=1):
            print(f"\nProcessing command {idx}: {sed_command}")

            # Extract target files from the sed command
            target_files = []
            try:
                parts = sed_command.split()
                for part in parts:
                    part_clean = part.rstrip(',;')
                    if os.path.exists(part_clean):
                        target_files.append(part_clean)

                if not target_files:
                    print(f"No valid files found in command: {sed_command}, skipping.")
                    continue

                backups = {}
                for target_file in target_files:
                    backup_path = os.path.join(tmpdirname, os.path.basename(target_file))
                    shutil.copy(target_file, backup_path)
                    backups[target_file] = backup_path

                # Apply the sed command (tentative)
                retcode, output = run_command(sed_command)
                if retcode != 0:
                    print(f"Failed to run command: {sed_command}, skipping.")
                    continue

                # Run cargo check and test again
                new_check_errors, new_check_warnings, new_test_errors, new_test_warnings = run_cargo_checks()

                # Determine error and warning differences
                new_total_errors = new_check_errors + new_test_errors

                print(f"New check errors: {new_check_errors}, New test errors: {new_test_errors}")

                # Ensure that errors never increase
                if new_total_errors > initial_total_errors:
                    print("Errors have increased after applying this sed command. Reverting the change.")
                    for target_file, backup_file in backups.items():
                        shutil.copy(backup_file, target_file)
                else:
                    print("Change does not increase errors. Keeping the change.")

            except Exception as e:
                print(f"Error processing sed command '{sed_command}': {e}")
                continue

    # After all sed commands, perform a final cargo check and test
    print("\nRunning final cargo check and test after applying all sed commands...")
    final_check_errors, final_check_warnings, final_test_errors, final_test_warnings = run_cargo_checks()

    final_total_errors = final_check_errors + final_test_errors

    print(f"Final check errors: {final_check_errors}, Final test errors: {final_test_errors}")

    # Compare final errors with initial errors
    if final_total_errors >= initial_total_errors:
        print("Final error count is the same or higher. Reverting all changes to the initial backup.")
        restore_rs_files(file_mapping)
    else:
        print("All sed commands applied successfully without increasing errors.")

    # Clean up the initial backup if no reversion was needed
    shutil.rmtree(initial_backup_dir)
    print("Process completed.")

if __name__ == "__main__":
    process_sed_commands()
