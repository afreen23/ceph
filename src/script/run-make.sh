#!/usr/bin/env bash

set -e

if ! [ "${_SOURCED_LIB_BUILD}" = 1 ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CEPH_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
    . "${CEPH_ROOT}/src/script/lib-build.sh" || exit 2
fi


trap clean_up_after_myself EXIT

ORIGINAL_CCACHE_CONF="$HOME/.ccache/ccache.conf"
SAVED_CCACHE_CONF="$HOME/.run-make-check-saved-ccache-conf"

function save_ccache_conf() {
    test -f $ORIGINAL_CCACHE_CONF && cp $ORIGINAL_CCACHE_CONF $SAVED_CCACHE_CONF || true
}

function restore_ccache_conf() {
    test -f $SAVED_CCACHE_CONF && mv $SAVED_CCACHE_CONF $ORIGINAL_CCACHE_CONF || true
}

function clean_up_after_myself() {
    rm -fr ${CEPH_BUILD_VIRTUALENV:-/tmp}/*virtualenv*
    restore_ccache_conf
}

function detect_ceph_dev_pkgs() {
    local cmake_opts="-DWITH_FMT_VERSION=9.0.0"
    local boost_root=/opt/ceph
    if test -f $boost_root/include/boost/config.hpp; then
        cmake_opts+=" -DWITH_SYSTEM_BOOST=ON -DBOOST_ROOT=$boost_root"
    else
        cmake_opts+=" -DBOOST_J=$(get_processors)"
    fi

    source /etc/os-release
    if [[ "$ID" == "ubuntu" ]]; then
        case "$VERSION" in
            *Xenial*)
                cmake_opts+=" -DWITH_RADOSGW_KAFKA_ENDPOINT=OFF";;
            *Focal*)
                cmake_opts+=" -DWITH_SYSTEM_ZSTD=ON";;
        esac
    fi
    echo "$cmake_opts"
}

function prepare() {
    local which_pkg="which"
    if command -v apt-get > /dev/null 2>&1 ; then
        which_pkg="debianutils"
    fi

    if test -f ./install-deps.sh ; then
        ci_debug "Running install-deps.sh"
        INSTALL_EXTRA_PACKAGES="ccache git $which_pkg clang"
        $DRY_RUN source ./install-deps.sh || return 1
        trap clean_up_after_myself EXIT
    fi

    if ! type ccache > /dev/null 2>&1 ; then
        echo "ERROR: ccache could not be installed"
        exit 1
    fi
}

function configure() {
    cat <<EOM
Note that the binaries produced by this script do not contain correct time
and git version information, which may make them unsuitable for debugging
and production use.
EOM
    save_ccache_conf
    # remove the entropy generated by the date/time embedded in the build
    $DRY_RUN export SOURCE_DATE_EPOCH="946684800"
    $DRY_RUN ccache -o sloppiness=time_macros
    $DRY_RUN ccache -o run_second_cpp=true
    if in_jenkins; then
        # Build host has plenty of space available, let's use it to keep
        # various versions of the built objects. This could increase the cache hit
        # if the same or similar PRs are running several times
        $DRY_RUN ccache -o max_size=100G
    else
        echo "Current ccache max_size setting:"
        ccache -p | grep max_size
    fi
    $DRY_RUN ccache -sz # Reset the ccache statistics and show the current configuration

    if ! discover_compiler ci-build ; then
        ci_debug "Failed to discover a compiler"
    fi
    local cxx_compiler="${discovered_cxx_compiler}"
    local c_compiler="${discovered_c_compiler}"
    local cmake_opts
    cmake_opts+=" -DCMAKE_CXX_COMPILER=$cxx_compiler -DCMAKE_C_COMPILER=$c_compiler"
    cmake_opts+=" -DCMAKE_CXX_FLAGS_DEBUG=-Werror"
    cmake_opts+=" -DENABLE_GIT_VERSION=OFF"
    cmake_opts+=" -DWITH_GTEST_PARALLEL=ON"
    cmake_opts+=" -DWITH_FIO=ON"
    cmake_opts+=" -DWITH_CEPHFS_SHELL=ON"
    cmake_opts+=" -DWITH_GRAFANA=ON"
    cmake_opts+=" -DWITH_SPDK=ON"
    cmake_opts+=" -DWITH_RBD_MIRROR=ON"
    if [ $WITH_SEASTAR ]; then
        cmake_opts+=" -DWITH_SEASTAR=ON"
    fi
    if [ $WITH_ZBD ]; then
        cmake_opts+=" -DWITH_ZBD=ON"
    fi
    if [ $WITH_RBD_RWL ]; then
        cmake_opts+=" -DWITH_RBD_RWL=ON"
    fi
    cmake_opts+=" -DWITH_RBD_SSD_CACHE=ON"

    cmake_opts+=$(detect_ceph_dev_pkgs)

    ci_debug "Our cmake_opts are: $cmake_opts"
    ci_debug "Running ./configure"
    ci_debug "Running do_cmake.sh"

    $DRY_RUN ./do_cmake.sh $cmake_opts $@ || return 1
}

function build() {
    local targets="$@"
    if test -n "$targets"; then
        targets="--target $targets"
    fi
    local bdir=build
    if [ "$BUILD_DIR" ]; then
        bdir="$BUILD_DIR"
    fi
    $DRY_RUN cd "${bdir}"
    BUILD_MAKEOPTS=${BUILD_MAKEOPTS:-$DEFAULT_MAKEOPTS}
    test "$BUILD_MAKEOPTS" && echo "make will run with option(s) $BUILD_MAKEOPTS"
    # older cmake does not support --parallel or -j, so pass it to underlying generator
    ci_debug "Running cmake"
    $DRY_RUN cmake --build . $targets -- $BUILD_MAKEOPTS || return 1
    $DRY_RUN ccache -s # print the ccache statistics to evaluate the efficiency
}

DEFAULT_MAKEOPTS=${DEFAULT_MAKEOPTS:--j$(get_processors)}

if [ "$0" = "$BASH_SOURCE" ]; then
    # not sourced
    if [ `uname` = FreeBSD ]; then
        GETOPT=/usr/local/bin/getopt
    else
        GETOPT=getopt
    fi

    options=$(${GETOPT} --name "$0" --options "" --longoptions "cmake-args:" -- "$@")
    if [ $? -ne 0 ]; then
        exit 2
    fi
    eval set -- "${options}"
    while true; do
        case "$1" in
            --cmake-args)
                cmake_args=$2
                shift 2;;
            --)
                shift
                break;;
            *)
                echo "bad option $1" >& 2
                exit 2;;
        esac
    done
    prepare
    configure "$cmake_args"
    build "$@"
fi
