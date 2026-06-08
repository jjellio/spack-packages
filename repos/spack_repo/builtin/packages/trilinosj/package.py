# Copyright Spack Project Developers. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import pathlib
import re
import sys
import shlex
import shutil
import tempfile
from contextlib import contextmanager


from spack_repo.builtin.build_systems.cmake import CMakePackage
from spack_repo.builtin.build_systems.cuda import CudaPackage
from spack_repo.builtin.build_systems.rocm import ROCmPackage
from spack_repo.builtin.packages.kokkos.package import Kokkos

from spack.package import *
from llnl.util import tty

# Trilinos is complicated to build, as an inspiration a couple of links to
# other repositories which build it:
# https://github.com/hpcugent/easybuild-easyblocks/blob/master/easybuild/easyblocks/t/trilinos.py#L111
# https://github.com/koecher/candi/blob/master/deal.II-toolchain/packages/trilinos.package
# https://gitlab.com/configurations/cluster-config/blob/master/trilinos.sh
# https://github.com/Homebrew/homebrew-science/blob/master/trilinos.rb and some
# relevant documentation/examples:
# https://github.com/trilinos/Trilinos/issues/175


class Trilinosj(CMakePackage, CudaPackage, ROCmPackage):
    """The Trilinos Project is an effort to develop algorithms and enabling
    technologies within an object-oriented software framework for the solution
    of large-scale, complex multi-physics engineering and scientific problems.
    A unique design feature of Trilinos is its focus on packages.
    """

    homepage = "https://trilinos.github.io"
    url = "https://github.com/trilinos/Trilinos/archive/refs/tags/trilinos-release-12-12-1.tar.gz"
    git = "https://github.com/trilinos/Trilinos.git"

    maintainers(
        "keitat",
        "kuberry",
        "jwillenbring",
        "psakievich",
        "ccober6",
        "fryeguy52",
        "sebrowne",
        "rppawlo",
        "cgcgcg",
    )

    tags = ["e4s"]

    # Default minimum free space required in the current temp dir.
    # Override with SPACK_TEMPDIR_MIN_FREE_SIZE, e.g. 15GB, 500MB, 20gb.
    default_tempdir_min_free_size = "15GB"

    # ###################### Versions ##########################

    version("master", branch="master")
    version("develop", branch="develop")

    # ###################### Variants ##########################

    # Build options
    variant("complex", default=False, description="Enable complex numbers in Trilinos")
    variant(
        "cuda_constexpr",
        default=False,
        description="Enable relaxed constexpr functions for CUDA build",
    )
    variant("cuda_rdc", default=False, description="Turn on RDC for CUDA build")
    variant("rocm_rdc", default=False, description="Turn on RDC for ROCm build")
    variant(
        "cxxstd",
        default="20",
        description="C++ standard",
        values=["20"],
        multi=False,
    )

    variant("openmp", default=False, description="Enable OpenMP")
    variant("shared", default=False, description="Enables the build of shared libraries")
    variant("uvm", default=False, when="@13.2: +cuda", description="Turn on UVM for CUDA build")
    variant("wrapper", default=False, description="Use nvcc-wrapper for CUDA build")

    variant("debug_symbols", default=True, description="Enable debug symbols (-g)")

    # CUDA without wrapper requires clang
    requires(
        "%clang",
        when="+cuda~wrapper",
        msg="trilinos~wrapper+cuda can only be built with the Clang compiler",
    )
    conflicts("+cuda_rdc", when="~cuda")
    conflicts("+rocm_rdc", when="~rocm")
    conflicts("+wrapper", when="~cuda")
    conflicts("+wrapper", when="%clang")


    # ###################### Dependencies ##########################

    depends_on("c", type="build")
    depends_on("cxx", type="build")

    depends_on("blas")
    depends_on("lapack")
    depends_on("boost")
    depends_on("cgns")
    depends_on("cmake@3.27:", type="build")
    depends_on("hdf5")
    depends_on("metis")
    depends_on("mpi")
    depends_on("netcdf-c")
    depends_on("parallel-netcdf")
    depends_on("parmetis")
    depends_on("superlu-dist")
    depends_on("zlib-api")

#    #depends_on("googletest", when="@17: +gtest")
    depends_on("kokkos-nvcc-wrapper", when="+wrapper")

    # spack will clone git repos into TMP/TMPDIR
    # the user-facing SPACK_ variables and even config
    # variables like spack build-stage are not where the
    # clone happens.
    # this presents two public variables a user can set
    # to control where git is staged
    #
    # export SPACK_LARGE_TMPDIR=/projects/trilinos/jjellio/tmpfs/tmp
    # export SPACK_TEMPDIR_MIN_FREE_SIZE=15GB
    def _parse_size(self, value):
        """Parse strings like 15GB, 500MB, 1024KB, 123456."""
        if value is None:
            raise ValueError("size value is None")

        value = value.strip()
        match = re.match(r"^(\d+)\s*([kmgt]?b?)?$", value, re.IGNORECASE)

        if not match:
            raise ValueError("invalid size: {0}".format(value))

        number = int(match.group(1))
        unit = (match.group(2) or "B").lower()

        multipliers = {
            "": 1,
            "b": 1,
            "k": 1024,
            "kb": 1024,
            "m": 1024 ** 2,
            "mb": 1024 ** 2,
            "g": 1024 ** 3,
            "gb": 1024 ** 3,
            "t": 1024 ** 4,
            "tb": 1024 ** 4,
        }

        if unit not in multipliers:
            raise ValueError("invalid size unit: {0}".format(unit))

        return number * multipliers[unit]

    def _format_size(self, num_bytes):
        """Human-readable byte count for warnings."""
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(num_bytes)

        for unit in units:
            if value < 1024 or unit == units[-1]:
                return "{0:.1f}{1}".format(value, unit)
            value /= 1024

    def _tempdir_min_free_size(self):
        value = os.environ.get(
            "SPACK_TEMPDIR_MIN_FREE_SIZE",
            self.default_tempdir_min_free_size,
        )

        try:
            return self._parse_size(value)
        except ValueError as err:
            tty.warn(
                "Ignoring invalid SPACK_TEMPDIR_MIN_FREE_SIZE={0!r}: {1}. "
                "Using package default {2}.".format(
                    value, err, self.default_tempdir_min_free_size
                )
            )
            return self._parse_size(self.default_tempdir_min_free_size)

    def _current_tempdir(self):
        # Reset tempfile cache so this reflects current TMPDIR/TMP/TEMP.
        tempfile.tempdir = None
        return tempfile.gettempdir()

    def _free_space(self, path):
        return shutil.disk_usage(path).free

    def _large_tmpdir_if_needed(self):
        current_tmpdir = self._current_tempdir()
        min_free = self._tempdir_min_free_size()
    
        try:
            free = self._free_space(current_tmpdir)
        except OSError as err:
            tty.warn(
                "Could not determine free space for temporary directory {0}: {1}. "
                "Not overriding TMPDIR.".format(current_tmpdir, err)
            )
            return None
    
        if free >= min_free:
            tty.debug(
                "Temporary directory {0} has {1} free, above required {2}; "
                "not overriding TMPDIR.".format(
                    current_tmpdir,
                    self._format_size(free),
                    self._format_size(min_free),
                )
            )
            return None
    
        large_tmpdir = os.environ.get("SPACK_LARGE_TMPDIR")
    
        if not large_tmpdir:
            tty.warn(
                "Temporary directory {0} has only {1} free, below requested "
                "minimum {2}, but SPACK_LARGE_TMPDIR is not set. Continuing "
                "without overriding TMPDIR.".format(
                    current_tmpdir,
                    self._format_size(free),
                    self._format_size(min_free),
                )
            )
            return None
    
        try:
            mkdirp(large_tmpdir)
        except OSError as err:
            tty.warn(
                "SPACK_LARGE_TMPDIR is set to {0}, but that directory could not "
                "be created: {1}. Continuing without overriding TMPDIR.".format(
                    large_tmpdir, err
                )
            )
            return None
    
        if not os.path.isdir(large_tmpdir):
            tty.warn(
                "SPACK_LARGE_TMPDIR={0} exists but is not a directory. "
                "Continuing without overriding TMPDIR.".format(large_tmpdir)
            )
            return None
    
        if not os.access(large_tmpdir, os.W_OK | os.X_OK):
            tty.warn(
                "SPACK_LARGE_TMPDIR={0} is not writable/searchable. "
                "Continuing without overriding TMPDIR.".format(large_tmpdir)
            )
            return None
    
        try:
            large_free = self._free_space(large_tmpdir)
        except OSError as err:
            tty.warn(
                "SPACK_LARGE_TMPDIR is set to {0}, but free space could not "
                "be determined: {1}. Continuing without overriding TMPDIR.".format(
                    large_tmpdir, err
                )
            )
            return None
    
        if large_free < min_free:
            tty.warn(
                "SPACK_LARGE_TMPDIR={0} has only {1} free, below requested "
                "minimum {2}. Continuing without overriding TMPDIR.".format(
                    large_tmpdir,
                    self._format_size(large_free),
                    self._format_size(min_free),
                )
            )
            return None
    
        tty.warn(
            "Temporary directory {0} has only {1} free, below requested "
            "minimum {2}. Using SPACK_LARGE_TMPDIR={3} for fetch/stage "
            "temporary files.".format(
                current_tmpdir,
                self._format_size(free),
                self._format_size(min_free),
                large_tmpdir,
            )
        )
    
        return large_tmpdir

    @contextmanager
    def _maybe_use_large_tmpdir(self):
        large_tmpdir = self._large_tmpdir_if_needed()

        if not large_tmpdir:
            yield
            return

        saved = {
            "TMPDIR": os.environ.get("TMPDIR"),
            "TMP": os.environ.get("TMP"),
            "TEMP": os.environ.get("TEMP"),
        }

        try:
            os.environ["TMPDIR"] = large_tmpdir
            os.environ["TMP"] = large_tmpdir
            os.environ["TEMP"] = large_tmpdir

            # Python caches tempfile.gettempdir(), so force it to re-evaluate.
            tempfile.tempdir = None

            yield

        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

            tempfile.tempdir = None

    def do_fetch(self, mirror_only=False):
        with self._maybe_use_large_tmpdir():
            return super().do_fetch(mirror_only)


    def flag_handler(self, name, flags):
        spec = self.spec

        if name == "cxxflags":
            if "+wrapper" in spec:
                flags.append("--expt-extended-lambda")
        #elif name == "ldflags":

        return (flags, None, None)

    def url_for_version(self, version):
        url = "https://github.com/trilinos/Trilinos/archive/refs/tags/trilinos-release-{0}.tar.gz"
        return url.format(version.dashed)

    @property
    def kokkos_cxx(self) -> str:
        if self.spec.satisfies("+wrapper"):
            return self["kokkos-nvcc-wrapper"].kokkos_cxx
        # Assumes build-time globals have been set already
        return spack_cxx

    def setup_build_environment(self, env: EnvironmentModifications) -> None:
        spec = self.spec
        if "+cuda" in spec and "+wrapper" in spec:
            if "+mpi" in spec:
                env.set("OMPI_CXX", self["kokkos-nvcc-wrapper"].kokkos_cxx)
                env.set("MPICH_CXX", self["kokkos-nvcc-wrapper"].kokkos_cxx)
                env.set("MPICXX_CXX", self["kokkos-nvcc-wrapper"].kokkos_cxx)
            else:
                env.set("CXX", self["kokkos-nvcc-wrapper"].kokkos_cxx)

        env.set("SPACK_COMPILER_FLAGS_REPLACE", "")
        env.set("SPACK_STORE_RPATH_DIRS", "")
    
    def tribits_tpl_library_args(self, tpl_name: str, dep: str) -> list[str]:
        """Generate TriBITS discovery args from a named Spack dependency.
    
        Use <TPL>_LIBRARY_DIRS and <TPL>_LIBRARY_NAMES so CMake still validates
        libraries with find_library(), while dep_spec.libs supplies the complete,
        ordered consumer link interface for the concrete Spack dependency.
    
        If the dependency is not present in this concrete spec, emit no args.
        """
    
        if not isinstance(dep, str):
            raise TypeError(
                f"dep must be a Spack dependency name string, got {type(dep).__name__}"
            )
    
        if dep not in self.spec:
            return []
    
        dep_spec = self.spec[dep]
        tpl_libs = dep_spec.libs
    
        if not tpl_libs:
            raise RuntimeError(
                f"{tpl_name}: dependency {dep_spec} is present, "
                f"but {dep_spec.name}.libs returned no libraries"
            )

        return [
            self.define(f"TPL_ENABLE_{tpl_name}", True),
            self.define(f"{tpl_name}_LIBRARY_NAMES",
                        ";".join(tpl_libs.names)),
            self.define(f"{tpl_name}_LIBRARY_DIRS",
                        ";".join(tpl_libs.directories)),
        ]

    # this is cruft to handle link openmp when openblas depends on it
    # spack needs to fix this, as by default openblas will link libopenblas
    # technically you also need to add -fopenmp atleast to the *link* flags
    def _dedupe_preserve_order(self, items: list[str]) -> list[str]:
        return list(dict.fromkeys(items))
    
    
    def blas_lapack_thread_link_flags(self) -> list[str]:
        """Return extra final-link flags needed by BLAS/LAPACK providers.
    
        This intentionally handles only compiler/runtime link interfaces that
        should not be modeled as ordinary Spack LibraryList entries.
    
        Current special case:
          openblas threads=openmp -> compiler OpenMP link flag
        """
    
        flags: list[str] = []
        seen: set[str] = set()
    
        for dep_name in ("blas", "lapack"):
            if dep_name not in self.spec:
                continue
    
            dep_spec = self.spec[dep_name]
    
            # BLAS and LAPACK often resolve to the same OpenBLAS provider.
            try:
                provider_key = dep_spec.dag_hash()
            except Exception:
                provider_key = str(dep_spec)
    
            if provider_key in seen:
                continue
    
            seen.add(provider_key)
    
            if not dep_spec.satisfies("openblas"):
                continue
    
            if dep_spec.satisfies("threads=openmp"):
                openmp_flag = dep_spec.package.compiler.openmp_flag
    
                if not openmp_flag:
                    raise RuntimeError(
                        f"{dep_name} resolves to {dep_spec}, which was built with "
                        "threads=openmp, but its compiler has no OpenMP flag"
                    )
    
                flags.extend(shlex.split(openmp_flag))
    
            elif dep_spec.satisfies("threads=pthreads"):
                # Optional, depending on whether your downstream link already
                # handles pthreads elsewhere.
                if not dep_spec.satisfies("platform=windows"):
                    flags.append("-lpthread")
    
        return self._dedupe_preserve_order(flags)

    @run_before("cmake")
    def write_hdf5_compat_file(self):
        compat = join_path(self.stage.path, "spack-hdf5-compat.cmake")

        with open(compat, "w") as f:
            f.write(r"""
include_guard(GLOBAL)

find_package(HDF5 CONFIG REQUIRED)

if(NOT TARGET HDF5::HDF5)
  add_library(HDF5::HDF5 INTERFACE IMPORTED)

  set(_hdf5_compat_libs)

  foreach(_t IN ITEMS
      hdf5::hdf5_hl-shared
      hdf5::hdf5_hl-static
      hdf5::hdf5_hl
      hdf5_hl-shared
      hdf5_hl-static
      hdf5_hl)
    if(TARGET "${_t}")
      list(APPEND _hdf5_compat_libs "${_t}")
      break()
    endif()
  endforeach()

  foreach(_t IN ITEMS
      hdf5::hdf5-shared
      hdf5::hdf5-static
      hdf5::hdf5
      hdf5-shared
      hdf5-static
      hdf5)
    if(TARGET "${_t}")
      list(APPEND _hdf5_compat_libs "${_t}")
      break()
    endif()
  endforeach()

  if(_hdf5_compat_libs)
    target_link_libraries(HDF5::HDF5 INTERFACE ${_hdf5_compat_libs})
  elseif(DEFINED HDF5_LIBRARIES)
    target_link_libraries(HDF5::HDF5 INTERFACE ${HDF5_LIBRARIES})
    if(DEFINED HDF5_INCLUDE_DIRS)
      set_target_properties(HDF5::HDF5 PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${HDF5_INCLUDE_DIRS}")
    endif()
  else()
    message(FATAL_ERROR
      "Could not synthesize HDF5::HDF5 from the HDF5 config package.")
  endif()
endif()
""")


    def cmake_args(self):
        options = []

        spec = self.spec
        define = self.define
        define_from_variant = self.define_from_variant
        cxx_flags = []
        c_flags = []
        linker_flags = []
        
        compat = join_path(self.stage.path, "spack-hdf5-compat.cmake")

        def _make_definer(prefix):
            def define_enable(suffix, value=None):
                key = prefix + suffix
                if value is None:
                    # Default to lower-case spec
                    value = suffix.lower()
                elif isinstance(value, bool):
                    # Explicit true/false
                    return define(key, value)
                return define_from_variant(key, value)

            return define_enable

        # Return "Trilinos_ENABLE_XXX" for spec "+xxx" or boolean value
        define_trilinos_enable = _make_definer("Trilinos_ENABLE_")
        # Same but for TPLs
        define_tpl_enable = _make_definer("TPL_ENABLE_")


        if "+debug_symbols" in spec:
            # debug symbols in rocm 6.4.x is broken
            if self.spec.satisfies("+rocm ^hip@6.4:6.4"):
                cxx_flags.append("-gline-tables-only")
                c_flags.append("-gline-tables-only")
            else:
                cxx_flags.append("-g")
                c_flags.append("-g")

        # #################### Base Settings #######################

        options.extend(
            [
                define_from_variant("BUILD_SHARED_LIBS", "shared"),
                define_trilinos_enable("ALL_OPTIONAL_PACKAGES", False),
                define_trilinos_enable("ALL_PACKAGES", False),
                define_trilinos_enable("EXAMPLES", False),
                define_trilinos_enable("SECONDARY_TESTED_CODE", True),
                define_trilinos_enable("TESTS", False),
                define_trilinos_enable("Fortran", False),
                define_from_variant("CMAKE_CXX_STANDARD", "cxxstd"),
                # Include after project() has enabled languages, before the rest of
                # the project's CMake/TriBITS logic proceeds.
                # this is a workaround because netcdf-c will call find package
                # on hdf5, but it does it in the wrong order. Specifically
                # it delcares it's own library interface first, then HDF5, and MPI
                # the prior is how a library should be linked - but cmake interfaces
                # need to be declared from the bottom up. e.g. MPI -> HDF5 -> netcdf
                # you will find 'compat' generated in a helper function
                # I also patch the order of library definitions in netcdf-c's cmake module
                # this address two things: it resolves HDF5::HDF5 vs hdf5::hdf5,
                # and it ensures the library interface order is correct
                #
                # if you omit this, you will find missing library declarations at the end of configure
                self.define("CMAKE_PROJECT_INCLUDE", compat),
                ]
        )


        # ################## Trilinos Packages #####################

        options.extend([
            # this would be what empire wants
            self.define("Trilinos_ENABLE_Panzer", True),
            self.define("Trilinos_ENABLE_PanzerMiniEM", True),
            # this is if you want to include mini-em, which could be a variant
            self.define("PanzerMiniEM_ENABLE_EXAMPLES", True),
        
            # this gets you SPARC's block tridiag
            self.define("Trilinos_ENABLE_Ifpack2", True),
            self.define("Ifpack2_ENABLE_EXAMPLES", True),
        
            # we technically do not need to explicitly enable these
            self.define("Trilinos_ENABLE_MueLu", True),
            self.define("Trilinos_ENABLE_Teko", True),
            self.define("Trilinos_ENABLE_Belos", True),
            self.define("Trilinos_ENABLE_Amesos2", True),
            self.define("Trilinos_ENABLE_Stratimikos", True),
        
            self.define("Trilinos_ENABLE_Intrepid2", True),
            self.define("Trilinos_ENABLE_Phalanx", True),
            self.define("Trilinos_ENABLE_Sacado", True),
        
            self.define("Trilinos_ENABLE_STK", True),
            self.define("Trilinos_ENABLE_SEACAS", True),
        

        ])

        options.extend(
            [
                define("CMAKE_C_COMPILER", self.spec["mpi"].mpicc),
                define("CMAKE_CXX_COMPILER", self.spec["mpi"].mpicxx),
                self.define("CMAKE_SKIP_RPATH", True),
                self.define("CMAKE_SKIP_BUILD_RPATH", True)
            ]
        )

        # the helper will return a list of required libs
        # extend expects a single list, so we unpack as we go
        options.extend([
            define("CMAKE_FIND_LIBRARY_SUFFIXES", ".a"),
            *self.tribits_tpl_library_args("BLAS", "blas"),
            *self.tribits_tpl_library_args("LAPACK", "lapack"),
            *self.tribits_tpl_library_args("ParMETIS", "parmetis"),
            *self.tribits_tpl_library_args("METIS", "metis"),
            *self.tribits_tpl_library_args("BOOST", "boost"),
            *self.tribits_tpl_library_args("CGNS", "cgns"),
            *self.tribits_tpl_library_args("HDF5", "hdf5"),
            define("Netcdf_ALLOW_MODERN", True),
            define("HDF5_ROOT", self.spec["hdf5"].prefix),
            define("CMAKE_FIND_PACKAGE_PREFER_CONFIG", True),
            *self.tribits_tpl_library_args("NETCDF", "netcdf-c"),
            *self.tribits_tpl_library_args("PNetCDF", "parallel-netcdf"),
            *self.tribits_tpl_library_args("SUPERLUDIST", "superlu-dist"),
            # I don't want matio
            self.define("TPL_ENABLE_Matio", False),
            # MPI is assumed on
            self.define("TPL_ENABLE_MPI", True),
            define("MPI_BASE_DIR", str(pathlib.PurePosixPath(spec["mpi"].prefix))),
        ])

        # spack does not propagate link flags in a sane way
        # if a dependent package uses openmp, we need the open flags at link time
        # a more sane method woudl be for spack to have "OpenMP" as a class
        # packages inherit from, and impose properties .libs .link_flags in packages
        # so that we could so something like self.spec.link_flags to have spack aggregate
        # linker flags across all dependent specs.
        # what we absolutely DO NOT WANT is to compile adding openmp flags to the compiler flags
        # I know based on what I've enabled, that OpenBLAS will use OpenMP
        # what I don't know is the openmp flag / libs used (gnu, llvm, etc..)
        # my helper function attempts to reconcile this
        linker_flags.extend(self.blas_lapack_thread_link_flags())
        

        options.append(define_trilinos_enable("Gtest", False))
        options.append(define_trilinos_enable("gtest", False))
        options.append(define_trilinos_enable("GTest", False))

        # ################# Explicit template instantiation #################

        complex_s = spec.variants["complex"].value

        options.extend([
            define("Teuchos_ENABLE_COMPLEX", complex_s),

            define("Tpetra_INST_DOUBLE", True),
            define("Tpetra_INST_COMPLEX_DOUBLE", complex_s),
            ])

        # ################# Kokkos ######################
        define_kok_enable = _make_definer("Kokkos_ENABLE_")

        # CPU target
        arch = Kokkos.get_microarch(spec.target, spec["kokkos"] if "kokkos" in spec else None)
        if arch:
            options.append(define("Kokkos_ARCH_" + arch.upper(), True))

        if "+openmp" in spec:
            options.extend(
                [
                    define_kok_enable("OPENMP" if spec.version >= Version("13") else "OpenMP"),
                ]
            )
        # trilinos extra linker flags is different from linker flags
        # these are things that make sense on the link line for Trilinos
        # but could break general link options used in CMake's setup phases
        # in practice, the cray-mpich libraries and GTL would make sense
        # required as MPI's libraries... and found in that manner

        trilinos_link_flags = []
        if spec.satisfies("+rocm ^cray-mpich") or spec.satisfies("+rcuda ^cray-mpich"):
            gtl_lib = spec["cray-mpich"].package.gtl_lib
            trilinos_link_flags.extend(gtl_lib["ldflags"])
            trilinos_link_flags.extend(gtl_lib["ldlibs"])

        if "+cuda" in spec:
            use_uvm = "+uvm" in spec
            options.extend([
                    define_kok_enable("CUDA", True),
                    define_kok_enable("CUDA_UVM", use_uvm),
                    define_kok_enable("CUDA_LAMBDA", True),
                    define_kok_enable("CUDA_CONSTEXPR", "cuda_constexpr"),
                    define_kok_enable("CUDA_RELOCATABLE_DEVICE_CODE", "cuda_rdc"),
                    define("Tpetra_INST_CUDA", True),
                    # this would be a variant +device_tpls or something like that
                    define_tpl_enable("CUBLAS", True),
                    define_tpl_enable("CUSOLVER", True),
                    define_tpl_enable("CUSPARSE", True)
                ])

            arch_map = Kokkos.spack_cuda_arch_map
            for arch in spec.variants["cuda_arch"].value:
              options.append(define("Kokkos_ARCH_" + arch_map[arch][0].upper(), True))

        if "+rocm" in spec:
            options.extend(
                [
                    define_kok_enable("HIP", True),
                    define_kok_enable("HIP_RELOCATABLE_DEVICE_CODE", "rocm_rdc"),
                    define("Tpetra_INST_HIP", True),

                    # this would be a variant +device_tpls or something like that
                    # TPLS - do I need to still tell KK to use them?
                    define_tpl_enable("ROCBLAS", True),
                    define_tpl_enable("ROCSOLVER", True),
                    define_tpl_enable("ROCSPARSE", True),
                    # GPU specific Trilinos - would make more sense to Trilinos
                    # to enable this by default in the correct cases..
                    define("Sacado_ENABLE_HIERARCHICAL_DFAD", True),
                ])

            cxx_flags.append("--offload-new-driver -x hip -mllvm -amdgpu-early-inline-all=false -mllvm -amdgpu-function-calls=false")
            linker_flags.append("--offload-new-driver -x none --hip-link -fuse-ld=lld -Wl,--image-base=0x20000000 -Wl,-z,common-page-size=0x200000 -Wl,-z,max-page-size=0x200000 -Wl,--whole-archive,-lhugetlbfs,--no-whole-archive")
            amdgpu_arch_map = Kokkos.amdgpu_arch_map
            for amd_target in spec.variants["amdgpu_target"].value:
                try:
                    arch = amdgpu_arch_map[amd_target][0]
                except KeyError:
                    pass
                else:
                    options.append(define("Kokkos_ARCH_" + arch.upper(), True))

            # this should add -L rocm/lib rocm/llvm/lib and rpath it
            rocm_prefix = spec["hip"].prefix.up
            
            linker_flags.append("-L{0}".format(rocm_prefix.lib))
            linker_flags.append("-Wl,-rpath,{0}".format(rocm_prefix.lib))
            linker_flags.append("-Wl,-rpath,{0}".format(rocm_prefix.llvm.lib))

            # this like this, do not work, so the prior just forms the rpath manually
            #linker_flags.extend(spec["hip"].package.libs.ld_flags.split())
            #linker_flags.extend(spec["hip"].libs)
            #linker_flags.extend(spec["llvm-amdgpu"].package.libs.ld_flags.split())

        # disable runpath and because some packages depend on pthreads and m, allow them as needed
        trilinos_link_flags += [" -Wl,--disable-new-dtags,--as-needed,-lpthread,-lm,--no-as-needed "]

        # always link via c++, we are a c++ project
        options.append(define("CMAKE_LINKER", self.spec["mpi"].mpicxx))
        if linker_flags:
            options.extend([
                self.define("CMAKE_EXE_LINKER_FLAGS",    " ".join(linker_flags)),
                self.define("CMAKE_SHARED_LINKER_FLAGS", " ".join(linker_flags))
            ])

        if cxx_flags:
            options.append(
                self.define("CMAKE_CXX_FLAGS", " ".join(cxx_flags))
            )

        if c_flags:
            options.append(
                self.define("CMAKE_C_FLAGS", " ".join(c_flags))
            )

        if trilinos_link_flags:
            options.append(self.define("Trilinos_EXTRA_LINK_FLAGS",
                                        " ".join(trilinos_link_flags)))

        for i, arg in enumerate(options):
            if not isinstance(arg, str):
                raise TypeError("cmake_args()[{}] is {}: {!r}".format(i, type(arg).__name__, arg))

        return options
