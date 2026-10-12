"""Spec 012 US2: build log (make V=1 / libtool / Yocto log.do_compile) -> compile commands."""
from pathlib import Path

import pytest

from tcadvisor.index.build_log import NO_COMMANDS_HINT, parse_build_log, write_compile_db
from tcadvisor.models import PrerequisiteError


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "ws"
    for rel in ("lib/remote.c", "app/main.c", "src/util.cpp"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("int x;\n")
    return repo


def test_libtool_plain_and_directory_tracking(tmp_path):
    repo = _repo(tmp_path)
    b = tmp_path / "b"
    log = f"""make[1]: Entering directory '{b}/lib'
/bin/bash ../libtool  --tag=CC   --mode=compile gcc -DHAVE_CONFIG_H -I. -c -o r.lo `test -f 'remote.c' || echo '{repo}/lib/'`remote.c
libtool: compile:  gcc -DHAVE_CONFIG_H -I. -I.. -g -O2 -c {repo}/lib/remote.c  -fPIC -DPIC -o .libs/r.o
libtool: compile:  gcc -DHAVE_CONFIG_H -I. -I.. -g -O2 -c {repo}/lib/remote.c -o r.o >/dev/null 2>&1
make[1]: Leaving directory '{b}/lib'
make[1]: Entering directory '{b}/app'
arm-poky-linux-gnueabi-gcc  -mthumb --sysroot=/sysroot -DHAVE_CONFIG_H -I. -I{repo}/lib -c -o m.o `test -f 'main.c' || echo '{repo}/app/'`main.c
ccache g++ -std=c++17 -c ../../ws/src/util.cpp -o util.o
echo gcc is great
gcc -o app m.o
make[1]: Leaving directory '{b}/app'
"""
    res = parse_build_log(log, repo)
    files = [e["file"] for e in res.entries]
    assert files == [str(repo / "lib/remote.c"), str(repo / "app/main.c"), str(repo / "src/util.cpp")]
    lib = res.entries[0]
    assert lib["directory"] == f"{b}/lib" and lib["arguments"][0] == "gcc" and "-fPIC" in lib["arguments"]
    assert f"-I{b}/lib" in lib["arguments"]  # relative include made absolute against the make directory
    app = res.entries[1]
    assert app["arguments"][0] == "arm-poky-linux-gnueabi-gcc" and "--sysroot=/sysroot" in app["arguments"]
    assert res.entries[2]["arguments"][0] == "g++"
    assert res.unmapped == []


def test_yocto_source_dir_is_mapped_automatically_and_explicitly(tmp_path):
    repo = _repo(tmp_path)
    s = "/yocto/tmp/work/cortexa9-poky-linux/remote/1.0-r0/git"
    log = f"make: Entering directory '/yocto/tmp/work/cortexa9-poky-linux/remote/1.0-r0/build'\n" \
          f"libtool: compile:  gcc -I{s}/lib -c {s}/lib/remote.c -o r.o\n"
    auto = parse_build_log(log, repo)
    assert auto.entries[0]["file"] == str(repo.resolve() / "lib/remote.c")
    assert auto.prefix_map == {s: str(repo.resolve())}
    assert f"-I{repo.resolve()}/lib" in auto.entries[0]["arguments"]
    explicit = parse_build_log(log, repo, src=s)
    assert explicit.entries[0]["file"] == str(repo.resolve() / "lib/remote.c")


def test_unmapped_and_empty_log(tmp_path):
    repo = _repo(tmp_path)
    res = parse_build_log("gcc -c /elsewhere/x.c -o x.o\n", repo)
    assert res.unmapped == ["/elsewhere/x.c"]
    log = tmp_path / "empty.log"
    log.write_text("make: Nothing to be done for 'all'.\n")
    with pytest.raises(PrerequisiteError, match="V=1"):
        write_compile_db(log, repo, tmp_path / "cc.json")
    assert "--disable-silent-rules" in NO_COMMANDS_HINT
