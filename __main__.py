#!/usr/bin/env python3

import re

from os.path import join
from sys import argv, exit, stderr
from argparse import ArgumentParser
from handpix import Handpix, ActionQueue

parser = ArgumentParser(description="A GTK GUI tool to assist in manually sorting images.")

parser.add_argument(
	"destination",
	help="destination directory",
)

parser.add_argument(
	"sources",
	help="directories from which to queue files",
	nargs="*",
)

parser.add_argument(
	"-D", "--delete-original",
	action="store_true",
	help="when copying files to destination, delete originals",
)

parser.add_argument(
	"-I", "--inclusive",
	action="store_true",
	help="include non-image filetypes (will not display thumbnail)",
)

parser.add_argument(
	"-v", "--verbose",
	action="store_true",
	help="TODO print debug output",
)

parser.add_argument(
	"-l", "--log",
	help="TODO specify which file to write debug output to",
)

parser.add_argument(
	"-r", "--recursive",
	action="store_true",
	help="recursively descend source directories when queueing files",
)

parser.add_argument(
	"-R", "--recycle-queue",
	action="store_true",
	help="when end of the queue is reached, requeue any skipped items",
)

parser.add_argument(
	"-P", "--relative",
	action="extend",
	help="specify a destination path relative to the path of the source",
	nargs=1,
)

parser.add_argument(
	"-t", "--threshold",
	default=2,
	help="hide delete confirmation prompt after this many consecutive deletes",
	nargs=1,
	type=int,
)

def criterion(string):
	lower = string.lower()
	if lower not in ActionQueue.SORT_DISPATCH:
		valid_values = ",".join(ActionQueue.SORT_FUNCTIONS.values())
		raise ValueError(
			"sort criterion must be one of %s" % (valid_values)
		)
	else:
		return lower

parser.add_argument(
	"-s", "--sort-by",
	default="name",
	help="specify queue sort criterion: atime, mtime, name, size, or random",
	type=criterion
)

_ASCENDING_PATTERN  = re.compile(r"^(a|asc|ascend|ascending)$")
_DESCENDING_PATTERN = re.compile(r"^(d|desc|descend|descending)$")

def order(string):
	lower = string.lower()
	if   _ASCENDING_PATTERN.fullmatch(lower):
		return False
	elif _DESCENDING_PATTERN.fullmatch(lower):
		return True
	else:
		raise ValueError(
			"sort order must be one of ascending or descending"
		)

parser.add_argument(
	"-o", "--sort-order",
	help="specify queue sort order: ascending or descending",
	default=False,
	type=order,
)

def re_type(regex):
	try:
		return re.compile(regex)
	except re.error as error:
		print(f"error compiling regex, {error}: {regex}", file=stderr)
		exit(1)

parser.add_argument(
	"-p", "--pattern",
	action="extend",
	help="specify one or more regular expressions; matching folders are treated as one item",
	nargs=1,
	type=re_type,
)

parser.add_argument(
	"-i", "--ignore",
	action="extend",
	help="specify one or more regular expressions; matching files and folders are ignored",
	nargs=1,
	type=re_type,
)

def main():
	args = parser.parse_args(argv[1:])

	if args.relative:
		for fragment in args.relative:
			args.sources.append(join(args.destination, fragment))

	Handpix(
		args.destination,
		args.sources,
		threshold=args.threshold,
		recursive=args.recursive,
		inclusive=args.inclusive,
		verbose=args.verbose,
		delete_original=args.delete_original,
		patterns=args.pattern if args.pattern else [],
		ignore=args.ignore if args.ignore else [],
		sort=args.sort_by,
		reverse=args.sort_order,
		recycle=args.recycle_queue,
	).run()

if __name__ == '__main__':
	main()
