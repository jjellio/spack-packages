export SPACK_ROOT=/tscratch/jjellio/eldorado/spack-dev/spack
export SPACK_PYTHON=/projects/aue/hpc/builds/x86_64/rhel8/f6a36cb8/tooling-sprint-24.02/install/linux-rhel8-x86_64/gcc-10.3.0/python-3.11.6-qvlrkva/bin/python3


host="$(hostname -s)"
cluster="${host%%[0-9]*}"
spack_tmp_path="/tmp"

if [[ "$cluster" == "hops" ]]; then
    mkdir -p /localdisk/devscratch/jjellio
    export TMPDIR=/localdisk/devscratch/jjellio
    spack_tmp_path=$TMPDIR
else
    v="my_${cluster}"
    export TMPDIR=/tmp/jjellio
    spack_tmp_path=/projects/trilinos/jjellio/tmpfs
    mkdir -p ${spack_tmp_path}
fi

mkdir -p ${TMPDIR}


export JJE_BASE=/tscratch/jjellio/eldorado/spack-dev/june-2026-hops
export SPACK_INSTALL_DIR=${JJE_BASE}/install
export SPACK_MODULE_DIR=${JJE_BASE}/modules
export SPACK_USER_CONFIG_PATH=${JJE_BASE}/config
export SPACK_USER_CACHE_PATH=${spack_tmp_path}/spack-cache
export SPACK_BUILD_STAGE_SIR=${spack_tmp_path}/stage
# spack clones to tmp, but on some machines tmp is very small
export SPACK_LARGE_TMPDIR=${spack_tmp_path}/tmp
export SPACK_TEMPDIR_MIN_FREE_SIZE=15GB

# I patched spack's cmake and autotools to respect a different
# level parallelism for install
export SPACK_INSTALL_PARALLELISM=1

mkdir -p ${SPACK_MODULE_DIR} ${SPACK_INSTALL_DIR} ${SPACK_USER_CONFIG_PATH}
source $SPACK_ROOT/share/spack/setup-env.sh
spack repo set --destination "$SPACK_ROOT/repos" builtin


spack env  activate ${SPACK_USER_CONFIG_PATH}
