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

    Args:
        command (str): The command to execute.

    Returns:
        tuple: (returncode, combined_output)
    """
    # Merge stderr into stdout to capture all output
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

    Args:
        output (str): The combined stdout and stderr from cargo commands.

    Returns:
        tuple: (errors, warnings)
    """
    errors = 0
    warnings = 0

    # Regex patterns
    compile_fail_pattern = re.compile(
        r'^error:\s+could not compile `.*?`.*?due to\s+(\d+)\s+previous error[s]?;?\s+(\d+)\s+warnings? emitted',
        re.IGNORECASE
    )
    individual_error_pattern = re.compile(r'^\s*error:\s+(?!\[E)')
    individual_warning_pattern = re.compile(r'^\s*warning:\s+(?!\[E)')

    for line in output.splitlines():
        # Debug: Print each line being processed
        # print(f"Processing line: {line}")

        # Handle 'could not compile' lines and extract error and warning counts
        compile_fail_match = compile_fail_pattern.match(line)
        if compile_fail_match:
            error_count = int(compile_fail_match.group(1))
            warning_count = int(compile_fail_match.group(2))
            errors += error_count
            warnings += warning_count
            print(f"Matched compile fail line: {line} with {error_count} errors and {warning_count} warnings")  # Debug
            continue  # Skip further processing for this line to prevent double counting

        # Match individual error lines
        if individual_error_pattern.search(line):
            errors += 1
            print(f"Matched individual error line: {line}")  # Debug

        # Match individual warning lines
        if individual_warning_pattern.search(line):
            warnings += 1
            print(f"Matched individual warning line: {line}")  # Debug

    return errors, warnings

def run_cargo_checks():
    """
    Runs 'cargo check' and 'cargo test', parsing their outputs.

    Returns:
        tuple: (check_errors, check_warnings, test_errors, test_warnings)
    """
    _, check_output = run_command("cargo check")
    check_errors, check_warnings = parse_cargo_output(check_output)

    _, test_output = run_command("cargo test")
    test_errors, test_warnings = parse_cargo_output(test_output)

    return check_errors, check_warnings, test_errors, test_warnings

def backup_directory(source_dir, backup_dir):
    """
    Creates a backup of the entire source directory.

    Args:
        source_dir (str): The directory to back up.
        backup_dir (str): The backup destination directory.
    """
    print(f"Creating initial backup of '{source_dir}' at '{backup_dir}'...")
    shutil.copytree(source_dir, backup_dir, dirs_exist_ok=True)
    print("Initial backup created.")

def restore_directory(backup_dir, source_dir):
    """
    Restores the source directory from the backup.

    Args:
        backup_dir (str): The backup source directory.
        source_dir (str): The directory to restore to.
    """
    print(f"Restoring '{source_dir}' from backup '{backup_dir}'...")
    # Remove current source directory contents
    for item in os.listdir(source_dir):
        item_path = os.path.join(source_dir, item)
        if os.path.isfile(item_path) or os.path.islink(item_path):
            os.unlink(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
    # Copy backup contents back to source directory
    shutil.copytree(backup_dir, source_dir, dirs_exist_ok=True)
    print("Restoration complete.")

def process_sed_commands():
    """
    Processes sed commands to modify files conditionally based on cargo checks.
    Ensures that the number of errors never increases.
    Reverts to an initial backup if post-processing errors exceed initial counts.
    """
    # Determine the current working directory
    source_dir = os.getcwd()

    # Create a temporary directory for the initial backup
    initial_backup_dir = tempfile.mkdtemp(prefix="initial_backup_")
    backup_directory(source_dir, initial_backup_dir)

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
            # Clean up the initial backup before exiting
            shutil.rmtree(initial_backup_dir)
            return

        with open(sed_file, 'r') as file:
            sed_commands = [line.strip() for line in file.readlines() if line.strip()]

    # Initial cargo check and test to get baseline errors and warnings
    print("Running initial cargo check and test...")
    initial_check_errors, initial_check_warnings, initial_test_errors, initial_test_warnings = run_cargo_checks()

    print(f"Initial check errors: {initial_check_errors}, Initial check warnings: {initial_check_warnings}")
    print(f"Initial test errors: {initial_test_errors}, Initial test warnings: {initial_test_warnings}")

    # Temporary directory to store per-command backups
    with tempfile.TemporaryDirectory() as tmpdirname:
        for idx, sed_command in enumerate(sed_commands, start=1):
            print(f"\nProcessing command {idx}: {sed_command}")

            # Extract target files from the sed command
            target_files = []
            try:
                parts = sed_command.split()
                for part in parts:
                    # Remove any trailing commas or semicolons
                    part_clean = part.rstrip(',;')
                    # Assuming file paths come after the sed substitution pattern
                    # This might need adjustment based on actual sed command structure
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
                check_error_diff = initial_check_errors - new_check_errors
                check_warning_diff = initial_check_warnings - new_check_warnings
                test_error_diff = initial_test_errors - new_test_errors
                test_warning_diff = initial_test_warnings - new_test_warnings

                print(f"New check errors: {new_check_errors}, New check warnings: {new_check_warnings}")
                print(f"New test errors: {new_test_errors}, New test warnings: {new_test_warnings}")

                if new_check_errors > initial_check_errors or new_test_errors > initial_test_errors:
                    print("Errors have increased after applying this sed command. Reverting the change.")
                    # Restore from per-command backup
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

    print(f"Final check errors: {final_check_errors}, Final check warnings: {final_check_warnings}")
    print(f"Final test errors: {final_test_errors}, Final test warnings: {final_test_warnings}")

    # Compare final errors with initial errors
    if (final_check_errors > initial_check_errors) or (final_test_errors > initial_test_errors):
        print("Final error count exceeds initial error count. Reverting all changes to the initial backup.")
        restore_directory(initial_backup_dir, source_dir)
    else:
        print("All sed commands applied successfully without increasing errors.")

    # Clean up the initial backup if no reversion was needed
    shutil.rmtree(initial_backup_dir)
    print("Process completed.")

if __name__ == "__main__":
    process_sed_commands()
