#! /bin/sh

base=$(dirname $0)
cdiff=$base/../../cdiff.py
PYTHON=${PYTHON:-python}

testNormal() {
	for i in $base/files/*; do
		$PYTHON $cdiff --color=always $i/in.diff | diff -b $i/out -
		assertEquals 0 $?
	done
}

testSideBySide() {
	for i in $base/files/*; do
		$PYTHON $cdiff -s --color=always $i/in.diff | diff -b $i/out.side_by_side -
		assertEquals 0 $?
	done
}


testNoColorIsUntouched() {
	for i in $base/files/*; do
		$PYTHON $cdiff  $i/in.diff | diff $i/in.diff -ub -
		assertEquals 0 $?
	done
}

. `which shunit2`
