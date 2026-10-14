"""Authenticate a hosted browser fixture using its own disposable Docker config."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from uuid import uuid4

REGISTRY = "docker.io"
STATE_NAME = "browser-registry-state.json"
SECRET_NAMES = {"DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def identity(info):
    return [info.st_dev, info.st_ino]


def checked_file(fd):
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and info.st_size <= 65536,
            "Registry control file has unexpected ownership, links, type or size")
    return info


def open_file(path, flags=os.O_RDONLY, dir_fd=None):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=dir_fd)
    try:
        checked_file(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def path_matches(path, fd):
    require(identity(path.lstat()) == identity(os.fstat(fd)) and not path.is_symlink(),
            "Registry control path identity changed")


def read_json(path, dir_fd=None):
    fd = open_file(path, dir_fd=dir_fd)
    with os.fdopen(fd, "r") as stream:
        return json.load(stream)


def locations(state):
    value = os.environ.get("RUNNER_TEMP", "")
    require(bool(value) and not any(c in value for c in "\r\n\0"),
            "A single-line RUNNER_TEMP is required for owned registry configuration")
    base = Path(value)
    require(base.is_absolute() and base == base.resolve() and base.is_dir()
            and base.stat().st_uid == os.getuid(), "Unexpected runner temporary directory")
    require(state == base / STATE_NAME, "Unexpected registry state path")
    return base


def write_state(path, data, exclusive=False):
    flags = os.O_RDWR | (os.O_CREAT | os.O_EXCL if exclusive else 0)
    fd = open_file(path, flags)
    with os.fdopen(fd, "w") as stream:
        if path.name == STATE_NAME:
            if exclusive:
                data["state_identity"] = identity(os.fstat(fd))
            require(data.get("state_identity") == identity(checked_file(fd)),
                    "Registry state file identity changed")
        path_matches(path, fd)
        os.ftruncate(fd, 0)
        json.dump(data, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        checked_file(fd)
        path_matches(path, fd)


def owned_directory(config, owner):
    fd = os.open(config, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and info.st_mode & 0o077 == 0 and owner.get("config_identity") == identity(info),
                "Registry config ownership, privacy or identity changed")
        path_matches(config, fd)
        require(read_json("owner.json", dir_fd=fd) == owner, "Registry owner marker changed")
        return fd
    except BaseException:
        os.close(fd)
        raise


def remove_owned(config, owner):
    fd = owned_directory(config, owner)
    try:
        require(set(os.listdir(fd)) <= {"owner.json", "config.json"},
                "Unexpected file in the owned registry configuration")
        for name in os.listdir(fd):
            file_fd = open_file(name, dir_fd=fd)
            os.close(file_fd)
        for name in os.listdir(fd):
            os.unlink(name, dir_fd=fd)
        path_matches(config, fd)
        os.rmdir(config)
        require(not config.exists() and not config.is_symlink(), "Owned credential configuration still exists")
    finally:
        os.close(fd)


def docker(config, args, password=None):
    env = {key: value for key, value in os.environ.items() if key not in SECRET_NAMES}
    env["DOCKER_CONFIG"] = str(config)
    # The token is supplied only on stdin. Docker output may contain sensitive
    # diagnostics; retain only the exit code, never its bytes or their hashes.
    return subprocess.run(["docker", "--config", str(config), *args],
                          input=password, capture_output=True, timeout=60, env=env)


def prepare(state):
    base = locations(state)
    require(not state.exists() and not state.is_symlink(), "Registry state already exists")
    username, token = (os.environ.get(name, "") for name in ("DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"))
    require(all(value and value.strip() == value and not any(c in value for c in "\r\n\0")
                for value in (username, token)), "Both read-only Docker Hub credentials are required")
    env_path = Path(os.environ.get("GITHUB_ENV", ""))
    require(env_path.is_absolute() and env_path == env_path.resolve()
            and env_path.parent == base / "_runner_file_commands"
            and re.fullmatch("set_env_[0-9a-f-]{36}", env_path.name)
            and not any(c in str(env_path) for c in "\r\n\0"), "Expected runner-managed GITHUB_ENV is required")
    env_fd = open_file(env_path, os.O_WRONLY | os.O_APPEND)
    nonce = uuid4().hex
    config = base / ("browser-registry-" + nonce)
    try:
        config.mkdir(mode=0o700)
    except BaseException:
        os.close(env_fd)
        raise
    owner = {"nonce": nonce, "uid": os.getuid(), "generator_sha256": source_hash(),
             "registry": REGISTRY, "config": str(config), "config_identity": identity(config.stat())}
    try:
        write_state(config / "owner.json", owner, exclusive=True)
        data = {**owner, "status": "ALLOCATED"}
        write_state(state, data, exclusive=True)
    except BaseException:
        for path in config.iterdir():
            path.unlink()
        config.rmdir()
        os.close(env_fd)
        raise
    try:
        # Docker auto-detects a native credential helper for an empty config.
        # A nonempty auths map keeps storage in this owned file; the empty
        # placeholder provides no credential and is replaced by the login.
        write_state(config / "config.json", {
            "auths": {"https://index.docker.io/v1/": {"auth": ""}}
        }, exclusive=True)
        result = docker(config, ["login", "--username", username, "--password-stdin", REGISTRY],
                        password=(token + "\n").encode())
        require(type(result.returncode) is int, "Docker Hub login returned an invalid exit type")
        data["login_exit_code"] = result.returncode
        require(result.returncode == 0, "Docker Hub login returned a nonzero exit")
        directory_fd = owned_directory(config, owner)
        try:
            credential_fd = open_file("config.json", dir_fd=directory_fd)
            with os.fdopen(credential_fd, "r") as stream:
                require(os.fstat(credential_fd).st_mode & 0o077 == 0, "Registry credential file is not private")
                credentials = json.load(stream)
        finally:
            os.close(directory_fd)
        expected = base64.b64encode((username + ":" + token).encode()).decode()
        require(credentials == {"auths": {"https://index.docker.io/v1/": {"auth": expected}}},
                "Docker Hub credential configuration did not match the owned login")
        checked_file(env_fd)
        path_matches(env_path, env_fd)
        directory_fd = owned_directory(config, owner)
        os.close(directory_fd)
        os.write(env_fd, ("DOCKER_CONFIG=" + str(config) + "\n").encode())
        path_matches(env_path, env_fd)
        data["status"] = "AUTHENTICATED_CONFIG_VERIFIED"
        write_state(state, data)
        print("Owned Docker Hub authentication configuration verified")
    except BaseException:
        data["status"] = "PREPARATION_FAILED"
        write_state(state, data)
        raise
    finally:
        os.close(env_fd)


def cleanup(state):
    base = locations(state)
    state_fd = open_file(state)
    with os.fdopen(state_fd, "r") as stream:
        data = json.load(stream)
        require(data.get("state_identity") == identity(checked_file(state_fd)), "Registry state file identity changed")
    require(type(data) is dict and type(data.get("nonce")) is str
            and re.fullmatch("[0-9a-f]{32}", data["nonce"]), "Invalid registry owner identity")
    owner = {key: data.get(key) for key in ("nonce", "uid", "generator_sha256", "registry", "config", "config_identity")}
    require(type(owner["uid"]) is int and owner["uid"] == os.getuid()
            and owner["generator_sha256"] == source_hash() and owner["registry"] == REGISTRY,
            "Registry owner source or principal changed")
    config = base / ("browser-registry-" + owner["nonce"])
    require(owner["config"] == str(config) and config == config.resolve(), "Registry config path changed")
    directory_fd = owned_directory(config, owner)
    os.close(directory_fd)
    logout_exit = None
    logout_error = False
    logout_attempted = False
    try:
        require(data.get("status") in {"ALLOCATED", "PREPARATION_FAILED", "AUTHENTICATED_CONFIG_VERIFIED"},
                "Unexpected registry preparation status")
        if data["status"] == "AUTHENTICATED_CONFIG_VERIFIED":
            directory_fd = owned_directory(config, owner)
            try:
                credentials = read_json("config.json", dir_fd=directory_fd)
            finally:
                os.close(directory_fd)
            require(type(credentials) is dict and set(credentials) == {"auths"}
                    and type(credentials["auths"]) is dict
                    and set(credentials["auths"]) == {"https://index.docker.io/v1/"},
                    "Registry cleanup refuses an unowned credential helper or configuration")
            entry = credentials["auths"]["https://index.docker.io/v1/"]
            require(type(entry) is dict and set(entry) == {"auth"} and type(entry["auth"]) is str
                    and bool(entry["auth"]), "Registry cleanup refuses an invalid credential entry")
            decoded = base64.b64decode(entry["auth"], validate=True)
            require(b":" in decoded and all(decoded.split(b":", 1)), "Registry cleanup refuses invalid credential bytes")
            logout_attempted = True
            result = docker(config, ["logout", REGISTRY])
            require(type(result.returncode) is int, "Docker Hub logout returned an invalid exit type")
            logout_exit = result.returncode
            require(logout_exit == 0, "Docker Hub logout returned a nonzero exit")
    except BaseException:
        logout_error = True
    finally:
        remove_owned(config, owner)
        data.update(status="REMOVED_WITH_LOGOUT_ERROR" if logout_error else "OWNED_CONFIG_REMOVED",
                    logout_exit_code=logout_exit, logout_attempted=logout_attempted, physical_config_removed=True)
        write_state(state, data)
    require(not logout_error, "Owned credentials removed; Docker Hub logout did not succeed")
    print("Owned Docker Hub credential configuration physically removed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "cleanup"))
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        (prepare if args.mode == "prepare" else cleanup)(args.state)
    except Exception:
        # Do not print Docker output, environment values, exception payloads,
        # config contents, or secret-derived hashes in hosted evidence.
        print("Owned registry authentication or cleanup refused; inspect the nonsensitive state status")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
