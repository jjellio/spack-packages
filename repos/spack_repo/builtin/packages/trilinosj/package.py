# Copyright Spack Project Developers. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import pathlib
import re
import sys
import shlex

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
    variant("shared", default=True, description="Enables the build of shared libraries")
    variant("uvm", default=False, when="@13.2: +cuda", description="Turn on UVM for CUDA build")
    variant("wrapper", default=False, description="Use nvcc-wrapper for CUDA build")

    variant("superlu-dist", default=False, description="Compile with SuperluDist solvers")
    variant("cusparse", default=False, description="Enable cuSPARSE support")
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

    # External Kokkos
    depends_on("kokkos~cuda", when="~cuda")
    depends_on("kokkos+wrapper", when="+wrapper")
    depends_on("kokkos~wrapper", when="~wrapper")
    depends_on("kokkos+pic~shared")
    depends_on("kokkos+cuda_relocatable_device_code", when="+cuda_rdc")
    depends_on("kokkos+hip_relocatable_device_code", when="+rocm_rdc")
    depends_on("kokkos-kernels+cusparse+cublas+cusolver+blas+lapack", when="+cuda")
    depends_on("kokkos-kernels+rocsparse+rocblas+rocsolver+blas+lapack", when="+rocm")
    depends_on("kokkos~complex_align")
    depends_on("kokkos@=5.0.2", when="@master:")
    depends_on("kokkos@=5.0.2", when="@17.0")
    depends_on("kokkos@=4.7.01", when="@16.2")
    depends_on("kokkos@=4.5.01", when="@16.1")
    depends_on("kokkos@=4.3.01", when="@16.0")
    depends_on("kokkos@=4.2.01", when="@15.1:15")
    depends_on("kokkos@=4.1.00", when="@14.4:15.0")
    depends_on("kokkos-kernels@=5.0.2", when="@master:")
    depends_on("kokkos-kernels@=5.0.2", when="@17.0")
    depends_on("kokkos-kernels@=4.7.01", when="@16.2")
    depends_on("kokkos-kernels@=4.5.01", when="@16.1")
    depends_on("kokkos-kernels@=4.3.01", when="@16.0")
    depends_on("kokkos-kernels@=4.2.01", when="@15.1:15")
    depends_on("kokkos+openmp", when="+openmp")

    for a in CudaPackage.cuda_arch_values:
        arch_str = f"+cuda cuda_arch={a}"
        depends_on(f"kokkos{arch_str}", when=arch_str)
    for a in ROCmPackage.amdgpu_targets:
        arch_str = f"+rocm amdgpu_target={a}"
        depends_on(f"kokkos{arch_str}", when=arch_str)


    depends_on("blas")
    depends_on("lapack")
    depends_on("boost+pic+system+icu~shared+program_options+graph+math+exception+stacktrace cxxstd=20")
    depends_on("cgns~base_scope~int64~ipo~legacy~mem_debug~fortran+hdf5+mpi+scoping+static~shared")
    depends_on("cmake@3.27:")
    #depends_on("googletest", when="@17: +gtest")
    depends_on("hdf5~cxx~threadsafe~java~fortran+hl+mpi~szip~shared")
    depends_on("kokkos-nvcc-wrapper", when="+wrapper")
    # depends_on('perl', type=('build',)) # TriBITS finds but doesn't use...
    depends_on("metis~gdb~int64~real64~shared")
    depends_on("mpi")
    depends_on("netcdf-c~hdf4~jna~dap+mpi+parallel-netcdf~shared~nczarr_zip build_system=cmake")
    depends_on("parallel-netcdf~cxx~burstbuffer~fortran~shared")
    depends_on("parmetis@=4.0.3~gdb~ipo~int64~shared")
    depends_on("superlu-dist", when="+superlu-dist")
    depends_on("zlib-ng~shared")

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

        if "+rocm" in spec:
            if "+mpi" in spec:
                env.set("OMPI_CXX", self.spec["hip"].hipcc)
                env.set("MPICH_CXX", self.spec["hip"].hipcc)
                env.set("MPICXX_CXX", self.spec["hip"].hipcc)
            else:
                env.set("CXX", self.spec["hip"].hipcc)
        
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

        if self.spec.satisfies("@master: +kokkos"):
            with open(
                os.path.join(self.stage.source_path, "packages", "kokkos", "CMakeLists.txt")
            ) as f:
                all_txt = f.read()
            r = dict(
                re.findall(r".*set\s?\(\s?Kokkos_VERSION_(MAJOR|MINOR|PATCH)\s?(\d+)", all_txt)
            )
            kokkos_version_in_trilinos_source = Version(
                ".".join([r["MAJOR"], r["MINOR"], r["PATCH"].zfill(2)])
            )
            kokkos_version_specified = spec["kokkos"].version
            if kokkos_version_in_trilinos_source != kokkos_version_specified:
                raise InstallError(
                    "For Trilinos@[master,develop], ^kokkos version in spec must "
                    "match version in Trilinos source code. Specify ^kokkos@{0} ".format(
                        kokkos_version_in_trilinos_source
                    )
                    + "for trilinos@[master,develop] instead of ^kokkos@{0}.\n".format(
                        kokkos_version_specified
                    )
                    + "Trilinos recipe maintainers, please update the ^kokkos version range"
                )

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
                # Include after project() has enabled languages, before the rest of
                # the project's CMake/TriBITS logic proceeds.
                self.define("CMAKE_PROJECT_INCLUDE", compat)
            ]
        )


        if spec.version >= Version("13"):
            options.append(define_from_variant("CMAKE_CXX_STANDARD", "cxxstd"))

        # ################## Trilinos Packages #####################

        options.extend([
            self.define("Trilinos_ENABLE_Panzer", True),
            self.define("Trilinos_ENABLE_PanzerMiniEM", True),
        
            self.define("Ifpack2_ENABLE_EXAMPLES", True),
            self.define("PanzerMiniEM_ENABLE_EXAMPLES", True),
        
            self.define("Trilinos_ENABLE_MueLu", True),
            self.define("Trilinos_ENABLE_Teko", True),
            self.define("Trilinos_ENABLE_Ifpack2", True),
            self.define("Trilinos_ENABLE_Belos", True),
            self.define("Trilinos_ENABLE_Amesos2", True),
            self.define("Trilinos_ENABLE_Stratimikos", True),
        
            self.define("Trilinos_ENABLE_Intrepid2", True),
            self.define("Trilinos_ENABLE_Phalanx", True),
            self.define("Trilinos_ENABLE_Sacado", True),
        
            self.define("Trilinos_ENABLE_STK", True),
            self.define("Trilinos_ENABLE_SEACAS", True),
        
            self.define("TPL_ENABLE_MPI", True),
            self.define("TPL_ENABLE_Matio", False),
            self.define("CMAKE_SKIP_RPATH", True),
            self.define("CMAKE_SKIP_BUILD_RPATH", True)
        ])

        # External Kokkos
        if spec.satisfies("@14.4.0: +kokkos"):
            options.append(define_tpl_enable("Kokkos"))
        if spec.satisfies("@15.1: +kokkos"):
            options.append(define_tpl_enable("KokkosKernels", True))

        options.extend(
            [
                define("CMAKE_C_COMPILER", self.spec["mpi"].mpicc),
                define("CMAKE_CXX_COMPILER", self.spec["mpi"].mpicxx),
                define("MPI_BASE_DIR", str(pathlib.PurePosixPath(spec["mpi"].prefix))),
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
            #define("HDF5_C_COMPILER_EXECUTABLE_NO_INTERROGATE", "{} -lhdf5 -hdf5_hl ".format(self.spec["mpi"].mpicc) ),
            #define("HDF5_C_COMPILER_EXECUTABLE",  "{} -lhdf5 -hdf5_hl ".format(self.spec["mpi"].mpicc)),
            *self.tribits_tpl_library_args("NETCDF", "netcdf-c"),
            *self.tribits_tpl_library_args("PNetCDF", "parallel-netcdf"),
            *self.tribits_tpl_library_args("SUPERLUDIST", "superlu-dist"),
        ])

        extra_link_flags = self.blas_lapack_thread_link_flags()
        
        if extra_link_flags:
            options.append(
                self.define("CMAKE_EXE_LINKER_FLAGS"," ".join(extra_link_flags))
            )

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

        if "+kokkos" in spec:
            arch = Kokkos.get_microarch(spec.target, spec["kokkos"] if "kokkos" in spec else None)
            if arch:
                options.append(define("Kokkos_ARCH_" + arch.upper(), True))

            define_kok_enable = _make_definer("Kokkos_ENABLE_")
            options.extend(
                [
                    define_kok_enable("CUDA"),
                    define_kok_enable("OPENMP" if spec.version >= Version("13") else "OpenMP"),
                ]
            )
            if "+cuda" in spec:
                use_uvm = "+uvm" in spec
                options.extend(
                    [
                        define_kok_enable("CUDA_UVM", use_uvm),
                        define_kok_enable("CUDA_LAMBDA", True),
                        define_kok_enable("CUDA_CONSTEXPR", "cuda_constexpr"),
                        define_kok_enable("CUDA_RELOCATABLE_DEVICE_CODE", "cuda_rdc"),
                    ]
                )
                arch_map = Kokkos.spack_cuda_arch_map
                options.extend(
                    define("Kokkos_ARCH_" + arch_map[arch][0].upper(), True)
                    for arch in spec.variants["cuda_arch"].value
                )

            if "+rocm" in spec:
                options.extend(
                    [
                        define_kok_enable("HIP", True),
                        define_kok_enable("HIP_RELOCATABLE_DEVICE_CODE", "rocm_rdc"),
                        define("Tpetra_INST_HIP", True),
                        define_tpl_enable("ROCBLAS", True),
                        define_tpl_enable("ROCSOLVER", True),
                        define_tpl_enable("ROCSPARSE", True)
                    ])

                amdgpu_arch_map = Kokkos.amdgpu_arch_map
                for amd_target in spec.variants["amdgpu_target"].value:
                    try:
                        arch = amdgpu_arch_map[amd_target][0]
                    except KeyError:
                        pass
                    else:
                        options.append(define("Kokkos_ARCH_" + arch.upper(), True))

        return options

    @run_after("install")
    def filter_python(self):
        # When trilinos is built with Python, libpytrilinos is included
        # through cmake configure files. Namely, Trilinos_LIBRARIES in
        # TrilinosConfig.cmake contains pytrilinos. This leads to a
        # run-time error: Symbol not found: _PyBool_Type and prevents
        # Trilinos to be used in any C++ code, which links executable
        # against the libraries listed in Trilinos_LIBRARIES.  See
        # https://github.com/trilinos/Trilinos/issues/569 and
        # https://github.com/trilinos/Trilinos/issues/866
        # A workaround is to remove PyTrilinos from the COMPONENTS_LIST
        # and to remove -lpytrilonos from Makefile.export.Trilinos
        if self.spec.satisfies("@:13.0.1 +python"):
            filter_file(
                r"(SET\(COMPONENTS_LIST.*)(PyTrilinos;)(.*)",
                (r"\1\3"),
                "%s/cmake/Trilinos/TrilinosConfig.cmake" % self.prefix.lib,
            )
            filter_file(r"-lpytrilinos", "", "%s/Makefile.export.Trilinos" % self.prefix.include)

    def setup_run_environment(self, env: EnvironmentModifications) -> None:
        if "+exodus" in self.spec:
            env.prepend_path("PYTHONPATH", self.prefix.lib)

