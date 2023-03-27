#!/bin/sh

# This script aims to build the minimal Qzone2TG pyz.
# before running the script, caller should export a `requirements.txt`,
# otherwise the script will call `poetry export` itself.
# `python3` and `pip3` is assumed to be available.

workdir=$1
mkdir -p ${workdir}

PIP_LOCK="${workdir}/requirements.txt"
PIP_TARG="${workdir}/.venv"

# export dependencies
if [ -f requirements.txt ]; then
    mv requirements.txt ${PIP_LOCK}
else
    poetry export -o ${PIP_LOCK} --without-hashes
fi


# install with pip
pip3 install -r ${PIP_LOCK} -t ${PIP_TARG} \
    --progress-bar off \
    --no-cache-dir
cp -r src/qzone3tg ${PIP_TARG}
cp ${PIP_TARG}/"qzone3tg/__main__.py" ${PIP_TARG}

# remove requirements.txt
rm ${PIP_LOCK}

for unittest in $(find ${PIP_TARG} -name "test*"); do
    if [ -d $unittest ]; then rm -r $unittest; fi
done

# move libs to top level
for depname in ${PIP_TARG}/*; do
    if [ -d $depname ]; then
        so=$(find $depname -regex '.*\.so\.?.*')
        if [[ $so != "" ]]; then mv $depname $workdir; fi
    fi
done

for pycache in $(find $workdir -name "__pycache__"); do
    rm -r $pycache
done

# zip app
python3 -m zipapp -o $workdir/app.pyz -c ${PIP_TARG}
rm -r ${PIP_TARG}
