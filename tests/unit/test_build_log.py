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


def test_failed_build_log_from_the_field(tmp_path):
    """A local build that stops at a missing target header (dlt/dlt.h) still logs the full compile command."""
    repo = tmp_path / "remotecontrolapp"
    (repo / "src/utils").mkdir(parents=True)
    (repo / "src/utils/Logger.cpp").write_text("int x;\n")
    b = repo / "b"
    b.mkdir()
    log = f"""make[1]: Entering directory '{b}'
/bin/sh ./libtool  --tag=CXX   --mode=compile g++ -DHAVE_CONFIG_H -I. -I..  -I/usr/include/servicelayer -I../src/utils -D_MORE_MARSHM -O2 -g -Wall -Werror -std=c++14 -fpermissive -DCAN_TYPE_DEFAULT    -g -O2 -MT libremotecontrolapp_la-Logger.lo -MD -MP -MF .deps/libremotecontrolapp_la-Logger.Tpo -c -o libremotecontrolapp_la-Logger.lo `test -f 'src/utils/Logger.cpp' || echo '../'`src/utils/Logger.cpp
libtool: compile:  g++ -DHAVE_CONFIG_H -I. -I.. -I/usr/include/servicelayer -I../src/utils -D_MORE_MARSHM -O2 -g -Wall -Werror -std=c++14 -fpermissive -DCAN_TYPE_DEFAULT -g -O2 -MT libremotecontrolapp_la-Logger.lo -MD -MP -MF .deps/libremotecontrolapp_la-Logger.Tpo -c ../src/utils/Logger.cpp  -fPIC -DPIC -o .libs/libremotecontrolapp_la-Logger.o
In file included from ../src/utils/Logger.cpp:14:
../src/utils/Logger.h:16:10: fatal error: dlt/dlt.h: No such file or directory
make[1]: *** [Makefile:639: libremotecontrolapp_la-Logger.lo] Error 1
make[1]: Leaving directory '{b}'
"""
    res = parse_build_log(log, repo)
    assert len(res.entries) == 1 and res.unmapped == []
    e = res.entries[0]
    assert e["file"] == str(repo / "src/utils/Logger.cpp") and e["directory"] == str(b)
    assert "-fPIC" in e["arguments"]  # libtool's echo replaces its wrapper call
    assert "-DCAN_TYPE_DEFAULT" in e["arguments"] and f"-I{repo}/src/utils" in e["arguments"]


def test_make_dry_run_lines(tmp_path):
    """`make -n` prints libtool wrapper calls and `&&`-joined, continued shell lines instead of running them."""
    repo = _repo(tmp_path)
    b = tmp_path / "b"
    log = f"""make[1]: Entering directory '{b}/lib'
/bin/bash ../libtool  --tag=CC   --mode=compile gcc -DX=1 -I. -c -o r.lo `test -f 'remote.c' || echo '{repo}/lib/'`remote.c
/bin/bash ../libtool  --tag=CC   --mode=link gcc -o libr.la r.lo
make[1]: Leaving directory '{b}/lib'
make[1]: Entering directory '{b}/src'
depbase=`echo util.o | sed 's|[^/]*$|.deps/&|;s|\\.o$||'`;\\
g++ -std=c++17 -DY -c -o util.o {repo}/src/util.cpp &&\\
mv -f $depbase.Tpo $depbase.Po
make[1]: Leaving directory '{b}/src'
"""
    res = parse_build_log(log, repo)
    assert [e["file"] for e in res.entries] == [str(repo / "lib/remote.c"), str(repo / "src/util.cpp")]
    assert res.entries[0]["arguments"][:2] == ["gcc", "-DX=1"]
    assert res.entries[1]["arguments"][0] == "g++" and "-DY" in res.entries[1]["arguments"]


_YOCTO = "/yocto/build/tmp-glibc/work/armv7at2hf-neon-oe-linux-gnueabi/remotecontrolapp/0.0-r0"


def _yocto_log(tick: str) -> str:
    """Shape of a real Yocto log.do_compile (field report): cross libtool with a prefix, wrapper call first, its
    `compile:` echo later (-j interleaving), source in ${WORKDIR}/remotecontrolapp, build in ${WORKDIR}/build."""
    w, b = _YOCTO, f"{_YOCTO}/build"
    flags = (f"-march=armv7-a -mthumb -mfpu=neon -mfloat-abi=hard --sysroot={w}/recipe-sysroot -DHAVE_CONFIG_H -I. "
             "-I../remotecontrolapp -I/usr/include/servicelayer -I../remotecontrolapp/src/features "
             "-I../remotecontrolapp/src/utils -std=c++14 -fpermissive -DCAN_TYPE_GEN2P -DEE_ARCH_GEN2P "
             f"-DREGION_PCB26 -I{w}/recipe-sysroot/usr/include/servicelayer -Werror=address")
    lines = ["DEBUG: Executing shell function do_compile", "NOTE: make -j 10", "make  all-am",
             f"make[1]: Entering directory '{b}'"]
    for f in ("src/utils/AppProperty.cpp", "src/features/RemoteDoorLock.cpp"):
        lines.append(f"./arm-oe-linux-gnueabi-libtool  --tag=CXX   --mode=compile arm-oe-linux-gnueabi-g++  -pie -fPIE "
                     f"{flags} -c -o x.lo {tick}test -f '{f}' || echo '../remotecontrolapp/'{tick}{f}")
    for f in ("src/utils/AppProperty.cpp", "src/features/RemoteDoorLock.cpp"):
        lines.append(f"arm-oe-linux-gnueabi-libtool: compile:  arm-oe-linux-gnueabi-g++ {flags} -c "
                     f"../remotecontrolapp/{f}  -fPIC -DPIC -o .libs/x.o")
        lines.append(f"arm-oe-linux-gnueabi-libtool: compile:  arm-oe-linux-gnueabi-g++ {flags} -c "
                     f"../remotecontrolapp/{f} -pie -fPIE -o x.o >/dev/null 2>&1")
    lines += [f"./arm-oe-linux-gnueabi-libtool  --tag=CXX   --mode=link arm-oe-linux-gnueabi-g++ -o lib.la x.lo",
              f"make[1]: Leaving directory '{b}'", "DEBUG: Shell function do_compile finished"]
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("tick", ["`", ""])  # real log / a copy that lost its backticks
def test_yocto_cross_log_with_source_outside_the_workspace(tmp_path, tick):
    repo = tmp_path / "tsu-src" / "apps" / "remotecontrolapp"  # the developer's checkout, not ${S}
    for rel in ("src/utils/AppProperty.cpp", "src/features/RemoteDoorLock.cpp"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("int x;\n")
    res = parse_build_log(_yocto_log(tick), repo)
    assert [e["file"] for e in res.entries] == [str(repo.resolve() / "src/utils/AppProperty.cpp"),
                                                str(repo.resolve() / "src/features/RemoteDoorLock.cpp")]
    assert res.prefix_map == {f"{_YOCTO}/remotecontrolapp": str(repo.resolve())} and res.unmapped == []
    a = res.entries[0]["arguments"]
    assert a[0] == "arm-oe-linux-gnueabi-g++" and "-fPIC" in a  # libtool's own (prefixed) echo is used
    assert {"-DCAN_TYPE_GEN2P", "-DEE_ARCH_GEN2P", "-DREGION_PCB26"} <= set(a)
    assert f"-I{repo.resolve()}/src/utils" in a  # source include dirs follow the source
    assert f"-I{_YOCTO}/build" in a  # build dir (config.h) stays where the build put it
    assert f"--sysroot={_YOCTO}/recipe-sysroot" in a
    assert res.entries[0]["directory"] == f"{_YOCTO}/build"


def test_cross_compiler_keeps_target_and_arch_flags():
    """Yocto cross builds: libclang parses for the build's target, so ARM sysroot headers resolve as in the build."""
    from tcadvisor.index.compile_db import _clean_args, cross_target
    assert cross_target("arm-oe-linux-gnueabi-g++") == "arm-oe-linux-gnueabi"
    assert cross_target("/opt/sdk/sysroots/x86_64/usr/bin/aarch64-poky-linux-gcc") == "aarch64-poky-linux"
    assert cross_target("g++") is None and cross_target("x86_64-linux-gnu-gcc-11") is None
    args = _clean_args(["arm-oe-linux-gnueabi-g++", "-march=armv7-a", "-mthumb", "-mfpu=neon", "-mfloat-abi=hard",
                        "-Werror=address", "-c", "x.cpp", "-o", "x.o"], "x.cpp", Path("/tmp"))
    assert args == ("--target=arm-oe-linux-gnueabi", "-march=armv7-a", "-mthumb", "-mfpu=neon", "-mfloat-abi=hard")
    assert _clean_args(["g++", "-march=native", "-c", "x.cpp"], "x.cpp", Path("/tmp")) == ()
