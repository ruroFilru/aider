import os
from rich.text import Text
from prompt_toolkit.completion import Completion


class Commands:
    def __init__(self, console, coder):
        self.console = console
        self.coder = coder

    def help(self):
        "Show help about all commands"
        commands = self.get_commands()
        for cmd in commands:
            cmd_method_name = f"cmd_{cmd[1:]}"
            cmd_method = getattr(self, cmd_method_name, None)
            if cmd_method:
                description = cmd_method.__doc__
                self.console.print(f"{cmd} {description}")
            else:
                self.console.print(f"{cmd} No description available.")

    def get_commands(self):
        commands = ["/help"]
        for attr in dir(self):
            if attr.startswith("cmd_"):
                commands.append("/" + attr[4:])

        return commands

    def do_run(self, cmd_name, args):
        cmd_method_name = f"cmd_{cmd_name}"
        cmd_method = getattr(self, cmd_method_name, None)
        if cmd_method:
            cmd_method(args)
        else:
            self.console.print(f"Error: Command {cmd_name} not found.")

    def get_command_completions(self, cmd_name, partial):
        cmd_completions_method_name = f"completions_{cmd_name}"
        cmd_completions_method = getattr(self, cmd_completions_method_name, None)
        if cmd_completions_method:
            for completion in cmd_completions_method(partial):
                yield completion

    def run(self, inp):
        words = inp.strip().split()
        if not words:
            return

        first_word = words[0]
        rest_inp = inp[len(words[0]) :]

        all_commands = self.get_commands()
        matching_commands = [cmd for cmd in all_commands if cmd.startswith(first_word)]
        if len(matching_commands) == 1:
            if matching_commands[0] == "/help":
                self.help()
            else:
                self.do_run(matching_commands[0][1:], rest_inp)
        elif len(matching_commands) > 1:
            self.console.print("[red]Ambiguous command: ', '.join(matching_commands)}")
        else:
            self.console.print(f"[red]Error: {first_word} is not a valid command.")

    def cmd_commit(self, args):
        "Commit edits to chat files made outside the chat (commit message optional)"

        if not self.coder.repo:
            self.console.print("[red]No git repository found.")
            return

        if not self.coder.repo.is_dirty():
            self.console.print("[red]No changes to commit.")
            return

        commit_message = args.strip()
        if commit_message:
            self.coder.repo.git.add(
                *[
                    os.path.relpath(fname, self.coder.repo.working_tree_dir)
                    for fname in self.coder.abs_fnames
                ]
            )
            self.coder.repo.git.commit("-m", commit_message, "--no-verify")
            commit_hash = self.coder.repo.head.commit.hexsha[:7]
            self.console.print(f"[red]{commit_hash} {commit_message}")
            return

        self.coder.commit()

    def cmd_undo(self, args):
        "Undo the last git commit if it was done by aider"
        if not self.coder.repo:
            self.console.print("[red]No git repository found.")
            return

        last_commit = self.coder.repo.head.commit
        if (
            not last_commit.message.startswith("aider:")
            or last_commit.hexsha[:7] != self.coder.last_aider_commit_hash
        ):
            self.console.print(
                "[red]The last commit was not made by aider in this chat session."
            )
            return
        self.coder.repo.git.reset("--hard", "HEAD~1")
        self.console.print(f"[red]Undid the last commit: {last_commit.message.strip()}")

    def cmd_diff(self, args):
        "Display the diff of the last aider commit"
        if not self.coder.repo:
            self.console.print("[red]No git repository found.")
            return

        if not self.coder.last_aider_commit_hash:
            self.console.print("[red]No previous aider commit found.")
            return

        commits = f"{self.coder.last_aider_commit_hash}~1"
        if self.coder.pretty:
            diff = self.coder.repo.git.diff(
                commits, "--color", self.coder.last_aider_commit_hash
            )
        else:
            diff = self.coder.repo.git.diff(commits, self.coder.last_aider_commit_hash)

        self.console.print(Text(diff))

    def cmd_add(self, args):
        "Add matching files to the chat"

        files = self.coder.get_all_relative_files()
        for word in args.split():
            matched_files = [file for file in files if word in file]
            if not matched_files:
                self.console.print(f"[red]No files matched '{word}'")
            for matched_file in matched_files:
                abs_file_path = os.path.abspath(
                    os.path.join(self.coder.root, matched_file)
                )
                if abs_file_path not in self.coder.abs_fnames:
                    self.coder.abs_fnames.add(abs_file_path)
                    self.console.print(f"[red]Added {matched_file} to the chat")
                else:
                    self.console.print(f"[red]{matched_file} is already in the chat")

    def completions_add(self, partial):
        files = set(self.coder.get_all_relative_files())
        files = files - set(self.coder.get_inchat_relative_files())
        for fname in files:
            if partial.lower() in fname.lower():
                yield Completion(fname, start_position=-len(partial))

    def completions_drop(self, partial):
        files = self.coder.get_inchat_relative_files()

        for fname in files:
            if partial.lower() in fname.lower():
                yield Completion(fname, start_position=-len(partial))

    def cmd_drop(self, args):
        "Remove matching files from the chat"

        for word in args.split():
            matched_files = [
                file
                for file in self.coder.abs_fnames
                if word in os.path.relpath(file, self.coder.root)
            ]
            if not matched_files:
                self.console.print(f"[red]No files matched '{word}'")
            for matched_file in matched_files:
                relative_fname = os.path.relpath(matched_file, self.coder.root)
                self.coder.abs_fnames.remove(matched_file)
                self.console.print(f"[red]Removed {relative_fname} from the chat")

    def cmd_ls(self, args):
        "List files and show their chat status"

        files = self.coder.get_all_relative_files()

        self.console.print("[red]Files in chat:\n")

        other_files = []
        for file in files:
            abs_file_path = os.path.abspath(os.path.join(self.coder.root, file))
            if abs_file_path in self.coder.abs_fnames:
                self.console.print(f"[red]  {file}")
            else:
                other_files.append(file)

        if not other_files:
            return

        self.console.print("\n[red]Other repo files:\n")

        for file in other_files:
            self.console.print(f"[red]  {file}")