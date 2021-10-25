import os
import platform
import subprocess
import textwrap

import pytest

from conan.tools.env import Environment
from conan.tools.env.environment import ProfileEnvironment
from conan.tools.microsoft.subsystems import WINDOWS
from conans.client.tools import chdir, environment_append
from conans.test.utils.mocks import ConanFileMock, MockSettings
from conans.test.utils.test_files import temp_folder
from conans.util.files import save


def test_compose():
    env = Environment()
    env.define("MyVar", "MyValue")
    env.define("MyVar2", "MyValue2")
    env.define("MyVar3", "MyValue3")
    env.define("MyVar4", "MyValue4")
    env.unset("MyVar5")

    env2 = Environment()
    env2.define("MyVar", "MyNewValue")
    env2.append("MyVar2", "MyNewValue2")
    env2.prepend("MyVar3", "MyNewValue3")
    env2.unset("MyVar4")
    env2.define("MyVar5", "MyNewValue5")

    env.compose_env(env2)
    env = env.vars(ConanFileMock())
    assert env.get("MyVar") == "MyValue"
    assert env.get("MyVar2") == 'MyValue2'
    assert env.get("MyVar3") == 'MyValue3'
    assert env.get("MyVar4") == "MyValue4"
    assert env.get("MyVar5") == ''


def test_define_append():
    env = Environment()
    env.define("MyVar", "MyValue")
    env.append("MyVar", "MyValue1")
    env.append("MyVar", ["MyValue2", "MyValue3"])
    assert env.vars(ConanFileMock()).get("MyVar") == "MyValue MyValue1 MyValue2 MyValue3"

    env = Environment()
    env.append("MyVar", "MyValue")
    env.append("MyVar", "MyValue1")
    env.define("MyVar", "MyValue2")
    assert env.vars(ConanFileMock()).get("MyVar") == "MyValue2"


@pytest.mark.parametrize("op1, v1, s1, op2, v2, s2, result",
                         [("define", "Val1", " ", "define", "Val2", " ", "Val1"),
                          ("define", "Val1", " ", "append", "Val2", " ", "Val1"),
                          ("define", "Val1", " ", "prepend", "Val2", " ", "Val1"),
                          ("define", "Val1", " ", "unset", "", " ", "Val1"),
                          ("append", "Val1", " ", "define", "Val2", " ", "Val2 Val1"),
                          ("append", "Val1", " ", "append", "Val2", " ", "MyVar Val2 Val1"),
                          ("append", "Val1", " ", "prepend", "Val2", " ", "Val2 MyVar Val1"),
                          ("append", "Val1", " ", "unset", "", " ", "Val1"),
                          ("prepend", "Val1", " ", "define", "Val2", " ", "Val1 Val2"),
                          ("prepend", "Val1", " ", "append", "Val2", " ", "Val1 MyVar Val2"),
                          ("prepend", "Val1", " ", "prepend", "Val2", " ", "Val1 Val2 MyVar"),
                          ("prepend", "Val1", " ", "unset", "", " ", "Val1"),
                          ("unset", "", " ", "define", "Val2", " ", ""),
                          ("unset", "", " ", "append", "Val2", " ", ""),
                          ("unset", "", " ", "prepend", "Val2", " ", ""),
                          ("unset", "", " ", "unset", "", " ", ""),
                          # different separators
                          ("append", "Val1", "+", "append", "Val2", "-", "MyVar+Val2+Val1"),
                          ("append", "Val1", "+", "prepend", "Val2", "-", "Val2+MyVar+Val1"),
                          ("unset", "", " ", "append", "Val2", "+", ""),
                          ("unset", "", " ", "prepend", "Val2", "+", ""),
                          ])
def test_compose_combinations(op1, v1, s1, op2, v2, s2, result):
    env = Environment()
    if op1 != "unset":
        getattr(env, op1)("MyVar", v1, s1)
    else:
        env.unset("MyVar")
    env2 = Environment()
    if op2 != "unset":
        getattr(env2, op2)("MyVar", v2, s2)
    else:
        env2.unset("MyVar")
    env.compose_env(env2)
    env = env.vars(ConanFileMock())
    with environment_append({"MyVar": "MyVar"}):
        assert env.get("MyVar") == result
    assert env._values["MyVar"].get_str("{name}", None, None) == result


@pytest.mark.parametrize("op1, v1, op2, v2, result",
                         [("define", "/path1", "define", "/path2", "/path1"),
                          ("define", "/path1", "append", "/path2", "/path1"),
                          ("define", "/path1", "prepend", "/path2", "/path1"),
                          ("define", "/path1", "unset", "", "/path1"),
                          ("append", "/path1", "define", "/path2", "/path2:/path1"),
                          ("append", "/path1", "append", "/path2", "MyVar:/path2:/path1"),
                          ("append", "/path1", "prepend", "/path2", "/path2:MyVar:/path1"),
                          ("append", "/path1", "unset", "", "/path1"),
                          ("prepend", "/path1", "define", "/path2", "/path1:/path2"),
                          ("prepend", "/path1", "append", "/path2", "/path1:MyVar:/path2"),
                          ("prepend", "/path1", "prepend", "/path2", "/path1:/path2:MyVar"),
                          ("prepend", "/path1", "unset", "", "/path1"),
                          ("unset", "", "define", "/path2", ""),
                          ("unset", "", "append", "/path2", ""),
                          ("unset", "", "prepend", "/path2", ""),
                          ("unset", "", "unset", "", ""),
                          ])
def test_compose_path_combinations(op1, v1, op2, v2, result):
    env = Environment()
    if op1 != "unset":
        getattr(env, op1+"_path")("MyVar", v1)
    else:
        env.unset("MyVar")
    env2 = Environment()
    if op2 != "unset":
        getattr(env2, op2+"_path")("MyVar", v2)
    else:
        env2.unset("MyVar")
    env.compose_env(env2)
    env = env.vars(ConanFileMock())
    assert env._values["MyVar"].get_str("{name}", None, pathsep=":") == result


def test_profile():
    myprofile = textwrap.dedent("""
        # define
        MyVar1=MyValue1
        #  append
        MyVar2+=MyValue2
        #  multiple append works
        MyVar2+=MyValue2_2
        #  prepend
        MyVar3=+MyValue3
        # unset
        MyVar4=!
        # Empty
        MyVar5=

        # PATHS
        # define
        MyPath1=(path)/my/path1
        #  append
        MyPath2+=(path)/my/path2
        #  multiple append works
        MyPath2+=(path)/my/path2_2
        #  prepend
        MyPath3=+(path)/my/path3
        # unset
        MyPath4=!

        # PER-PACKAGE
        mypkg*:MyVar2=MyValue2
        """)

    profile_env = ProfileEnvironment.loads(myprofile)
    env = profile_env.get_profile_env("")
    env = env.vars(ConanFileMock())
    with environment_append({"MyVar1": "$MyVar1",
                             "MyVar2": "$MyVar2",
                             "MyVar3": "$MyVar3",
                             "MyVar4": "$MyVar4"}):
        assert env.get("MyVar1") == "MyValue1"
        assert env.get("MyVar2", "$MyVar2") == '$MyVar2 MyValue2 MyValue2_2'
        assert env.get("MyVar3", "$MyVar3") == 'MyValue3 $MyVar3'
        assert env.get("MyVar4") == ""
        assert env.get("MyVar5") == ''

        env = profile_env.get_profile_env("mypkg1/1.0")
        env = env.vars(ConanFileMock())
        assert env.get("MyVar1") == "MyValue1"
        assert env.get("MyVar2", "$MyVar2") == 'MyValue2'


def test_env_files():
    env = Environment()
    env.define("MyVar", "MyValue")
    env.define("MyVar1", "MyValue1")
    env.append("MyVar2", "MyValue2")
    env.prepend("MyVar3", "MyValue3")
    env.unset("MyVar4")
    env.define("MyVar5", "MyValue5 With Space5=More Space5;:More")
    env.append("MyVar6", "MyValue6")  # Append, but previous not existing
    env.define_path("MyPath1", "/Some/Path1/")
    env.append_path("MyPath2", ["/Some/Path2/", "/Other/Path2/"])
    env.prepend_path("MyPath3", "/Some/Path3/")
    env.unset("MyPath4")
    folder = temp_folder()

    prevenv = {"MyVar1": "OldVar1",
               "MyVar2": "OldVar2",
               "MyVar3": "OldVar3",
               "MyVar4": "OldVar4",
               "MyPath1": "OldPath1",
               "MyPath2": "OldPath2",
               "MyPath3": "OldPath3",
               "MyPath4": "OldPath4",
               }

    display_bat = textwrap.dedent("""\
        @echo off
        echo MyVar=%MyVar%!!
        echo MyVar1=%MyVar1%!!
        echo MyVar2=%MyVar2%!!
        echo MyVar3=%MyVar3%!!
        echo MyVar4=%MyVar4%!!
        echo MyVar5=%MyVar5%!!
        echo MyVar6=%MyVar6%!!
        echo MyPath1=%MyPath1%!!
        echo MyPath2=%MyPath2%!!
        echo MyPath3=%MyPath3%!!
        echo MyPath4=%MyPath4%!!
        """)

    display_sh = textwrap.dedent("""\
        echo MyVar=$MyVar!!
        echo MyVar1=$MyVar1!!
        echo MyVar2=$MyVar2!!
        echo MyVar3=$MyVar3!!
        echo MyVar4=$MyVar4!!
        echo MyVar5=$MyVar5!!
        echo MyVar6=$MyVar6!!
        echo MyPath1=$MyPath1!!
        echo MyPath2=$MyPath2!!
        echo MyPath3=$MyPath3!!
        echo MyPath4=$MyPath4!!
        """)

    def check(cmd_):
        out, _ = subprocess.Popen(cmd_, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  env=prevenv, shell=True).communicate()
        out = out.decode()
        assert "MyVar=MyValue!!" in out
        assert "MyVar1=MyValue1!!" in out
        assert "MyVar2=OldVar2 MyValue2!!" in out
        assert "MyVar3=MyValue3 OldVar3!!" in out
        assert "MyVar4=!!" in out
        assert "MyVar5=MyValue5 With Space5=More Space5;:More!!" in out
        assert "MyVar6= MyValue6!!" in out  # The previous is non existing, append has space
        assert "MyPath1=/Some/Path1/!!" in out
        assert os.pathsep.join(["MyPath2=OldPath2", "/Some/Path2/", "/Other/Path2/!!"]) in out
        assert os.pathsep.join(["MyPath3=/Some/Path3/", "OldPath3!!"]) in out
        assert "MyPath4=!!" in out

        # This should be output when deactivated
        assert "MyVar=!!" in out
        assert "MyVar1=OldVar1!!" in out
        assert "MyVar2=OldVar2!!" in out
        assert "MyVar3=OldVar3!!" in out
        assert "MyVar4=OldVar4!!" in out
        assert "MyVar5=!!" in out
        assert "MyVar6=!!" in out
        assert "MyPath1=OldPath1!!" in out
        assert "MyPath2=OldPath2!!" in out
        assert "MyPath3=OldPath3!!" in out
        assert "MyPath4=OldPath4!!" in out

    with chdir(folder):
        if platform.system() == "Windows":
            env = env.vars(ConanFileMock())
            env.save_bat("test.bat")

            save("display.bat", display_bat)
            cmd = "test.bat && display.bat && deactivate_test.bat && display.bat"
            check(cmd)
            # FIXME: Powershell still not working
            # env.save_ps1("test.ps1", pathsep=":")
            # cmd = 'powershell.exe -ExecutionPolicy ./test.ps1; gci env:'
            # shell = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # (stdout, stderr) = shell.communicate()
            # stdout, stderr = decode_text(stdout), decode_text(stderr)
            # check(cmd)
        else:
            env = env.vars(ConanFileMock())
            env.save_sh("test.sh")
            save("display.sh", display_sh)
            os.chmod("display.sh", 0o777)
            cmd = '. ./test.sh && ./display.sh && . ./deactivate_test.sh && ./display.sh'
            check(cmd)


@pytest.mark.skipif(platform.system() != "Windows", reason="Requires Windows")
def test_windows_case_insensitive():
    # Append and define operation over the same variable in Windows preserve order
    env = Environment()
    env.define("MyVar", "MyValueA")
    env.define("MYVAR", "MyValueB")
    env.define("MyVar1", "MyValue1A")
    env.append("MYVAR1", "MyValue1B")
    env.define("MyVar2", "MyNewValue2")
    folder = temp_folder()

    display_bat = textwrap.dedent("""\
        @echo off
        echo MyVar=%MyVar%!!
        echo MyVar1=%MyVar1%!!
        echo MyVar2=%MyVar2%!!
        """)

    with chdir(folder):
        env = env.vars(ConanFileMock())
        env._subsystem = WINDOWS
        env.save_bat("test.bat")
        save("display.bat", display_bat)
        cmd = "test.bat && display.bat && deactivate_test.bat && display.bat"
        out, _ = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  shell=True, env={"MYVAR2": "OldValue2"}).communicate()

    out = out.decode()
    assert "MyVar=MyValueB!!" in out
    assert "MyVar=!!" in out
    assert "MyVar1=MyValue1A MyValue1B!!" in out
    assert "MyVar1=!!" in out
    assert "MyVar2=MyNewValue2!!" in out
    assert "MyVar2=OldValue2!!" in out


def test_dict_access():
    env = Environment()
    env.append("MyVar", "MyValue", separator="@")
    ret = env.vars(ConanFileMock()).items()
    assert dict(ret) == {"MyVar": "MyValue"}

    env = Environment()
    env.prepend("MyVar", "MyValue", separator="@")
    env_vars = env.vars(ConanFileMock())
    assert dict(env_vars.items()) == {"MyVar": "MyValue"}
    assert env_vars["MyVar"] == "MyValue"

    env2 = Environment()
    env2.define("MyVar", "MyValue2")
    env.compose_env(env2)
    env_vars = env.vars(ConanFileMock())
    assert dict(env_vars.items()) == {"MyVar": "MyValue@MyValue2"}

    with pytest.raises(KeyError):
        _ = env_vars["Missing"]

    # With previous values in the environment
    env = Environment()
    env.prepend("MyVar", "MyValue", separator="@")
    old_env = dict(os.environ)
    os.environ.update({"MyVar": "PreviousValue"})
    env_vars = env.vars(ConanFileMock())
    try:
        assert env_vars["MyVar"] == "MyValue@PreviousValue"
    finally:
        os.environ.clear()
        os.environ.update(old_env)

    env = Environment()
    env.append_path("MyVar", "MyValue")
    old_env = dict(os.environ)
    os.environ.update({"MyVar": "PreviousValue"})
    env_vars = env.vars(ConanFileMock())
    try:
        assert env_vars["MyVar"] == "PreviousValue{}MyValue".format(os.pathsep)
        with env_vars.apply():
            assert os.getenv("MyVar") == "PreviousValue{}MyValue".format(os.pathsep)
    finally:
        os.environ.clear()
        os.environ.update(old_env)

    assert list(env_vars.keys()) == ["MyVar"]
    assert dict(env_vars.items()) == {"MyVar": "MyValue"}


def test_env_win_bash():
    conanfile = ConanFileMock()
    conanfile.settings_build = MockSettings({"os": "Windows"})
    conanfile.win_bash = True
    conanfile.conf = {"tools.microsoft.bash:subsystem": "msys2"}
    folder = temp_folder()
    conanfile.folders.generators = folder
    env = Environment()
    env.define("MyVar", "MyValue")
    env.define_path("MyPath", "c:/path/to/something")
    env.append("MyPath", "D:/Otherpath")
    env_vars = env.vars(conanfile)
    env_vars.save_script("foo")
    content = open(os.path.join(folder, "foo.sh")).read()
    assert 'MyVar="MyValue"' in content
    # Note the unit letter is lowercase
    assert 'MyPath="/c/path/to/something:/d/otherpath"' in content


def test_public_access():
    env = Environment()
    env.define("MyVar", "MyValue")
    env.append("MyVar", "MyValue2")
    env.define_path("MyPath", "c:/path/to/something")
    env.append_path("MyPath", "D:/Otherpath")
    env_vars = env.vars(ConanFileMock())
    for name, values in env_vars.items():
        if name == "MyVar":
            assert values == "MyValue MyValue2"
        if name == "MyPath":
            assert values == "c:/path/to/something{}D:/Otherpath".format(os.pathsep)

    env.remove("MyPath", "D:/Otherpath")
    assert env_vars.get("MyPath") == "c:/path/to/something"


class TestProfileEnvRoundTrip:

    def test_define(self):
        myprofile = textwrap.dedent("""
            # define
            MyVar1=MyValue1
            MyPath1=(path)/my/path1
            """)

        env = ProfileEnvironment.loads(myprofile)
        text = env.dumps()
        assert text == textwrap.dedent("""\
            MyVar1=MyValue1
            MyPath1=(path)/my/path1
            """)

    def test_append(self):
        myprofile = textwrap.dedent("""
            # define
            MyVar1+=MyValue1
            MyPath1+=(path)/my/path1
            """)

        env = ProfileEnvironment.loads(myprofile)
        text = env.dumps()
        assert text == textwrap.dedent("""\
            MyVar1+=MyValue1
            MyPath1+=(path)/my/path1
            """)

    def test_prepend(self):
        myprofile = textwrap.dedent("""
            # define
            MyVar1=+MyValue1
            MyPath1=+(path)/my/path1
            """)

        env = ProfileEnvironment.loads(myprofile)
        text = env.dumps()
        assert text == textwrap.dedent("""\
            MyVar1=+MyValue1
            MyPath1=+(path)/my/path1
            """)

    def test_combined(self):
        myprofile = textwrap.dedent("""
            MyVar1=+MyValue11
            MyVar1+=MyValue12
            MyPath1=+(path)/my/path11
            MyPath1+=(path)/my/path12
            """)

        env = ProfileEnvironment.loads(myprofile)
        text = env.dumps()
        assert text == textwrap.dedent("""\
            MyVar1=+MyValue11
            MyVar1+=MyValue12
            MyPath1=+(path)/my/path11
            MyPath1+=(path)/my/path12
            """)

    def test_combined2(self):
        myprofile = textwrap.dedent("""
            MyVar1+=MyValue11
            MyVar1=+MyValue12
            MyPath1+=(path)/my/path11
            MyPath1=+(path)/my/path12
            """)

        env = ProfileEnvironment.loads(myprofile)
        text = env.dumps()
        # NOTE: This is reversed order compared to origin, prepend always first
        assert text == textwrap.dedent("""\
            MyVar1=+MyValue12
            MyVar1+=MyValue11
            MyPath1=+(path)/my/path12
            MyPath1+=(path)/my/path11
            """)
