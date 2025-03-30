from podman.domain.containers import Container as PodmanContainer

from enum import Enum
import multiprocessing
import os

class StepWorkdirType(Enum):
    CUSTOM = 1
    BUILDDIR = 2

class Step:
    def __init__(self, source_data, package):
        source_properties = source_data

        self.args: list[str] = source_properties["args"]
        self.cpu_count = multiprocessing.cpu_count()

        self.package = package

        if "workdir" in source_properties:
            self.workdir_type = StepWorkdirType.CUSTOM
            self.workdir: str = source_properties["workdir"]
        else:
            self.workdir_type = StepWorkdirType.BUILDDIR
            self.workdir: str = None

        if "environ" in source_properties:
            self.environ: dict[str, str] = source_properties["environ"]
        else:
            self.environ: dict[str, str] = {}

        if "shell" in source_properties:
            self.shell = source_properties["shell"]
        else:
            self.shell = False

    def do_substitutions(self, system_prefix, system_targets,  sources_dir, builds_dir, source_dir,  build_dir, collect_dir, system_root):
        replaced_args = []
        replaced_environ: dict[str, str]= {}

        base_workdir = build_dir
        if self.workdir_type == StepWorkdirType.BUILDDIR:
            replaced_workdir = base_workdir
        else:
            replaced_workdir = self.workdir

        source_dir = source_dir
        source_root = sources_dir
        build_root = builds_dir

        this_collect_dir = collect_dir

        sysroot_dir = system_root
        prefix_dir = system_prefix

        parallelism = self.cpu_count

        replaced_workdir = replaced_workdir.replace("@THIS_BUILD_DIR@", base_workdir)
        replaced_workdir = replaced_workdir.replace("@THIS_SOURCE_DIR@", source_dir)
        replaced_workdir = replaced_workdir.replace("@THIS_COLLECT_DIR@", this_collect_dir)

        replaced_workdir = replaced_workdir.replace("@BUILD_ROOT@", build_root)
        replaced_workdir = replaced_workdir.replace("@SOURCE_ROOT@", source_root)

        replaced_workdir = replaced_workdir.replace("@SYSROOT_DIR@", sysroot_dir)

        replaced_workdir = replaced_workdir.replace("@PREFIX@", prefix_dir)
        replaced_workdir = replaced_workdir.replace("@TARGET@", system_targets["x86_64"])
        replaced_workdir = replaced_workdir.replace("@PARALLELISM@", str(parallelism))

        for arg in self.args:
            arg = arg.replace("@THIS_SOURCE_DIR@", source_dir)
            arg = arg.replace("@THIS_COLLECT_DIR@", this_collect_dir)
            arg = arg.replace("@THIS_BUILD_DIR@", base_workdir)

            arg = arg.replace("@BUILD_ROOT@", build_root)
            arg = arg.replace("@SOURCE_ROOT@", source_root)
            
            arg = arg.replace("@SYSROOT_DIR@", sysroot_dir)

            arg = arg.replace("@PREFIX@", prefix_dir)
            arg = arg.replace("@TARGET@", system_targets["x86_64"])
            arg = arg.replace("@PARALLELISM@", str(parallelism))

            replaced_args.append(arg)

        for env_var, env_val in self.environ.items():
            env_val = env_val.replace("@THIS_SOURCE_DIR@", source_dir)
            env_val = env_val.replace("@THIS_COLLECT_DIR@", this_collect_dir)
            env_val = env_val.replace("@THIS_BUILD_DIR@", base_workdir)

            env_val = env_val.replace("@BUILD_ROOT@", build_root)
            env_val = env_val.replace("@SOURCE_ROOT@", source_root)

            env_val = env_val.replace("@SYSROOT_DIR@", sysroot_dir)

            env_val = env_val.replace("@PREFIX@", prefix_dir)
            env_val = env_val.replace("@TARGET@", system_targets["x86_64"])
            env_val = env_val.replace("@PARALLELISM@", str(parallelism))

            replaced_environ[env_var] = env_val     

        base_path = "/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games"
        if "PATH" in replaced_environ:
            replaced_environ['PATH'] = f"{prefix_dir}/bin:{replaced_environ['PATH']}:{base_path}"
        else:
            replaced_environ['PATH'] = f"{prefix_dir}/bin:{base_path}"

        replaced_environ['ACLOCAL_PATH'] = f"{prefix_dir}/share/aclocal"

        return replaced_args, replaced_environ, replaced_workdir

    def exec(self, system_prefix, system_targets,  sources_dir, builds_dir, source_dir,  build_dir, collect_dir, system_root, container: PodmanContainer):
        args, environ, workdir = self.do_substitutions(system_prefix, system_targets,  sources_dir, builds_dir, source_dir,  build_dir, collect_dir, system_root)

        return_code: int = None
        response: bytes = None

        if self.shell is True:
            return_code, response = container.exec_run(cmd = ['/bin/bash', '-c', *args], environment = environ, workdir = workdir,
                user='hbuild', tty=True)
        else:
            return_code, response = container.exec_run(cmd = args, environment = environ, workdir = workdir,
                user='hbuild', tty=True)
            
        print(response.decode())
        if return_code > 0:
            raise Exception(f"Error running step for package {self.package.name}: exit {return_code}")
        
    def __str__(self):
        return f"Step: {self.environ} {self.args}: {self.workdir}"

    def __repr__(self):
        return self.__str__()