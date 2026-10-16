"""Fixed CLI errors never echo unrecognized credential-bearing arguments."""
import argparse


class PrivateArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        # A prefix such as --database-url must never be read as --database-url-env.
        kwargs.setdefault('allow_abbrev', False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        self.exit(2, 'Invalid worker arguments; use --help for --database-url or --database-url-env options.\n')
