RUNNING_PLATFORM="${READ_MET_OFFICE_ENV:-shell}"

echo "Running in $RUNNING_PLATFORM"

DEBUG=
DEBUG=echo

if ${DEBUG};
then
  echo "Running in debug mode";
else
  echo "Running in normal mode";
fi

if [ "${RUNNING_PLATFORM}" == "docker" ];
then
    DATA_ROOT="/";
else
    DATA_ROOT="./";
fi

export DATA_PATH=${DATA_PATH:=${DATA_ROOT}data}
INPUTS=${DATA_PATH}/inputs
OUTPUTS=${DATA_PATH}/outputs

$DEBUG rm -r ${OUTPUTS}

python -u read_ea.py
python -u write_output_metadata.py

