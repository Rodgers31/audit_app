"""Bounded operator arguments with errors that never echo private inputs."""
import argparse
import sys


class CLIInputError(ValueError):
    pass


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CLIInputError()


def bounded_arguments(argv):
    arguments = sys.argv[1:] if argv is None else argv
    if (type(arguments) is not list or len(arguments) > 16
            or any(type(item) is not str or len(item) > 2048
                   or any(ord(char) < 32 or ord(char) == 127 for char in item)
                   for item in arguments)):
        raise CLIInputError()
    return arguments
