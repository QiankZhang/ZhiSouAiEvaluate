#! /bin/bash

RUN_MODE=${1:-make}

PYTHON_PATH="/data1/minisearch/guoliang21/miniforge3/bin/python3"


if [ "$RUN_MODE" = "make" ]; then
    $PYTHON_PATH -m bin.make_data
    $PYTHON_PATH -m bin.process_data
fi
