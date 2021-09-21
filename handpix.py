#!/usr/bin/python3

import os
import re
import shutil
import random

from sys import exit
from enum import Enum, auto
from itertools import chain
from pathlib import Path

from typing import List, Optional, Set, Tuple

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk, Gdk, GdkPixbuf

try:
	import resources as RESOURCES
except ModuleNotFoundError as error:
	if __name__ != '__main__':
		raise ModuleNotFoundError(
			"Resources Module 'resources.py' "
			"has not been generated, as such this module cannot be imported. "
			"Please run this module standalone in its native directory first "
			"in order to generate the resources module."
		)

def generate_resources() -> None:
	resources = ""
	resources += f"DEFAULT_IMAGE_BYTES = {Path('missing.png').read_bytes()}\n"
	resources += f"GLADE_DATA = \"\"\"{Path('handpix.glade').read_text()}\"\"\"\n"
	Path('resources.py').write_text(resources)

if __name__ == '__main__':
	generate_resources()
	exit(0)

_SUPPORTED_IMAGE_FORMATS = set()
for file_format in GdkPixbuf.Pixbuf.get_formats():
	for extension in file_format.get_extensions():
		_SUPPORTED_IMAGE_FORMATS.add(extension)

_HUMANSIZE_SUFFIXES = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]

def humansize(nbytes: int) -> str:
	i = 0
	while nbytes >= 1024 and i < len(_HUMANSIZE_SUFFIXES) - 1:
		nbytes /= 1024
		i += 1
	f = ("%.2f" % nbytes).rstrip("0").rstrip(".")
	return "%s %s" % (f, _HUMANSIZE_SUFFIXES[i])

def checkbox_property(attrname: str) -> property:

	def fget(self):
		value = getattr(self, attrname).get_active()
		# print(f"get {attrname} = {value}")
		return value
	
	def fset(self, value):
		# print(f"set {attrname} = {value}")
		getattr(self, attrname).set_active(value)
	
	return property(fget=fget, fset=fset)

class ImageSet(object):

	SUPPORTED_IMAGE_FORMATS = _SUPPORTED_IMAGE_FORMATS

	SUPPORTED_TEXT_FORMATS  = {"txt", "json", "xml", "html", "md"}

	# DEFAULT_IMAGE = GdkPixbuf.Pixbuf.new_from_file("missing.png")

	DEFAULT_IMAGE = GdkPixbuf.Pixbuf.new_from_stream(
		Gio.MemoryInputStream.new_from_bytes(
			GLib.Bytes(RESOURCES.DEFAULT_IMAGE_BYTES)
		)
	)

	DEFAULT_TEXT  = (
		"Either the set is empty or the select item is not a text file."
	)

	class Type(Enum):
		UNKNOWN = 0
		IMAGE   = 1
		TEXT    = 2

		@classmethod
		def from_extension(cls, extension):
			extension = extension.lower()
			if   extension in ImageSet.SUPPORTED_IMAGE_FORMATS:
				return ImageSet.Type.IMAGE
			elif extension in ImageSet.SUPPORTED_TEXT_FORMATS:
				return ImageSet.Type.TEXT
			else:
				return ImageSet.Type.UNKNOWN

	@classmethod
	def is_supported_format(cls, extension: str) -> bool:
		extension = extension.lower()
		return (
			extension in cls.SUPPORTED_IMAGE_FORMATS
				or
			extension in cls.SUPPORTED_TEXT_FORMATS
		)

	def __init__(self, path: Path):
		self.path            = path if isinstance(path, Path) else Path(path)
		self.is_collection   = False
		self.files           = []
		self.cache           = {}

		self.selected        = 0

		self.atime           = 0
		self.mtime           = 0
		self.name            = ""
		self.size            = 0

		# human readable size
		self.humansize       = "0 B total"

		self.load_from(path)

	def __repr__(self):
		return "ImageSet(%s)" % (self.path)

	def __len__(self):
		""" Return the number of files in the collection """
		return len(self.files)

	def next(self) -> None:
		""" Select the next file in the collection; wraps on final item """
		self.selected = (self.selected + 1) % len(self.files)

	def prev(self) -> None:
		""" Select the previous file in the collection; wraps on first item """
		length        = len(self.files)
		self.selected = (self.selected + (length - 1)) % length

	def get_progress_text(self) -> str:
		""" Return a string representation of the index """
		if not self.is_collection:
			return "single file"
		return "file %d of %d" % (
			self.selected + 1,
			len(self),
		)

	def get_image(self, image_size : Optional[int] = None) -> GdkPixbuf.Pixbuf:
		"""
		Return a pixbuf image for the currently selected file.

		If an image cannot be generated, such as in the case the file isn't
		an image file, then a default image is returned instead.
		"""
		
		if len(self.files) == 0:
			return ImageSet.DEFAULT_IMAGE

		if self.get_item_type() != ImageSet.Type.IMAGE:
			return ImageSet.DEFAULT_IMAGE

		file = self.files[self.selected]

		# generate a new pixbuf if one does not exist in the requested size
		if file not in self.cache or self.cache[file].get_width() != image_size:

			if ImageSet.Type.from_extension(file.suffix[1:]) is ImageSet.Type.IMAGE:
				try:
					pixbuf = GdkPixbuf.Pixbuf.new_from_file(bytes(file))

					# scale pixbuf based on orientation
					if pixbuf.get_height() >= pixbuf.get_width():
						# image is a square or in portrait orientation
						width  = image_size
						height = int(width * pixbuf.get_height() / pixbuf.get_width())
					else:
						# image is in landscape orientation
						height = image_size
						width  = int(height * pixbuf.get_width() / pixbuf.get_height())

					self.cache[file] = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
				except Exception as e:
					print(str(e))
					self.cache[file] = ImageSet.DEFAULT_IMAGE
			else:
				self.cache[file] = ImageSet.DEFAULT_IMAGE

		return self.cache[file]

	def get_text(self) -> str:
		"""
		Return a text representation for the currently selected file.

		If such text cannot be generated, such as in the case the file isn't
		a supported text file, then a default text is returned instead.
		"""

		if len(self.files) == 0:
			return ImageSet.DEFAULT_TEXT

		if self.get_item_type() != ImageSet.Type.TEXT:
			return ImageSet.DEFAULT_TEXT

		file = self.files[self.selected]

		if file not in self.cache:
			self.cache[file] = file.read_text()

		return self.cache[file]

	def get_item_name(self) -> str:
		""" Return the name of the selected file """

		if len(self.files) == 0:
			return (
				"This set has no files."
				"The folder is probably empty or has no files of a supported type."
			)

		return self.files[self.selected].name

	def get_item_type(self) -> str:
		""" Return the type of the selected file based on its extension """
		return ImageSet.Type.from_extension(
			self.files[self.selected].suffix[1:]
		)

	def load_from(self, filepath: Path, inclusive: bool = False) -> None:
		"""
		Load a collection of files from given path. If the path points to a file
		that file will be loaded, and if the the path points to a folder, each
		eligable file in that folder will be loaded.

		By default, only image file formats that can be displayed as a pixbuf
		will be loaded. To load all files regardless of type, True must be
		passed to the inclusive parameter. Collection size in bytes is always
		computed using all files in the collection regardless of type.
		"""

		self.files.clear()

		self.name  = filepath.name

		stat       = os.stat(filepath)
		self.atime = stat.st_atime
		self.mtime = stat.st_mtime

		self.path  = filepath

		self.is_collection = filepath.is_dir()

		if self.is_collection:

			self.size = 0
			for child in filepath.iterdir():

				if child.is_dir():
					continue

				stat       = os.stat(child)
				self.size += stat.st_size

				if inclusive or ImageSet.is_supported_format(child.suffix[1:]):
					self.files.append(child)

			# sort them by name to make viewing
			# sequential sets more bearable
			self.files.sort()

		else:
			self.size = stat.st_size
			self.files.append(filepath)

		self.humansize = humansize(self.size) + " total"

	def pathparts(self) -> Tuple[str, str]:
		"""
		Return a tuple of the path to the select file's parent directory and a
		string representing the selected file's name with the extension removed.
		"""
		return self.path.parent, self.path.name

class ActionQueue(object):

	class Action(Enum):
		START    = auto()
		SKIP     = auto()
		DELETE   = auto()
		SELECT   = auto()

	class History(object):

		def __init__(self,
			kind   : "ActionQueue.Action",
			target : ImageSet,
			next   : Optional["History"] = None,
			prev   : Optional["History"] = None
		):
			self.kind   = kind
			self.target = target
			self.next   = next
			self.prev   = prev

		def __repr__(self, depth: int = 0, limit: int = 3):
			text = f"History({self.kind}, {self.target})\n"
			if self.prev is not None and depth < limit:
				return text + self.prev.__repr__(depth=depth + 1)
			else:
				return text

		def __eq__(self, other: "History"):
			return self.kind == other.kind and self.target == other.target

	class PathCollision(Exception):
		pass

	SORT_DISPATCH = {
		"atime"  : lambda imgset: imgset.atime,
		"mtime"  : lambda imgset: imgset.mtime,
		"name"   : lambda imgset: imgset.name,
		"size"   : lambda imgset: imgset.size,
		"random" : lambda imgset: random.random(),
	}

	def __init__(self):
		self.queue         = []
		self.skipped       = []
		self.deleted       = []
		self.selected      = {}
		self.history_start = ActionQueue.History(ActionQueue.Action.START, None)
		self.history       = self.history_start

	def __len__(self):
		return len(self.queue)

	def get_progress(self) -> float:
		processed = len(self.skipped) + len(self.deleted) + sum(len(values) for values in self.selected.values())
		pending   = len(self.queue)
		total     = pending + processed
		return 1.0 - (pending / total)

	def get_item_status(self) -> str:
		if self.history.next:
			status = self.history.next

			if   status.kind == ActionQueue.Action.SKIP:
				return "skipped"
			elif status.kind == ActionQueue.Action.DELETE:
				return "deleted"
			elif status.kind == ActionQueue.Action.SELECT:
				return status.target.parents[0].name
			else:
				return "error"
		else:
			return "unsorted"

	UNDO_DISPATCH = {
		Action.START  : lambda queue: None,
		Action.SKIP   : lambda queue: queue.__back(),
		Action.DELETE : lambda queue: queue.__undelete(),
		Action.SELECT : lambda queue: queue.__unselect(queue.history.target),
	}

	def undo(self) -> bool:
		""" Undo the previous call to the skip, delete, or select methods """
		if self.history.kind is ActionQueue.Action.START:
			return False

		ActionQueue.UNDO_DISPATCH[self.history.kind](self)
		self.history = self.history.prev
		return True

	REDO_DISPATCH = {
		Action.START  : lambda queue: None,
		Action.SKIP   : lambda queue: queue.__skip(),
		Action.DELETE : lambda queue: queue.__delete(),
		Action.SELECT : lambda queue: queue.__select(queue.history.target, True),
	}

	def redo(self) -> bool:
		"""
		Recommit the most previously undone call to the skip, delete, or select
		methods. Does not redo modifications to history, so if a history node
		is modified after the fact, it's deleted.
		"""

		if self.history.next is None:
			return False

		self.history = self.history.next
		ActionQueue.REDO_DISPATCH[self.history.kind](self)
		return True

	def sort(self, criterion : str = "name", reverse : bool = False) -> None:
		# this is conceptually a queue, but we're treating the end as the beginning so
		# the internal sort order should be inverse of what the user supplies us with
		self.queue.sort(key=ActionQueue.SORT_DISPATCH[criterion], reverse=not reverse)

	def peek(self) -> ImageSet:
		""" Return the item in the front of the queue without removing it """
		return self.queue[-1] if len(self.queue) != 0 else None

	def add(self,
		path                : Path,
		recursive           : bool             = False,
		inclusive           : bool             = False,
		formats             : Set[str]         = ImageSet.SUPPORTED_IMAGE_FORMATS,
		collection_patterns : List[re.Pattern] = [],
		ignore_patterns     : List[re.Pattern] = [],
	) -> None:

		for dirpath, dirnames, filenames in os.walk(Path(path).expanduser()):

			dirpath = Path(dirpath)

			for filename in filenames:

				# filter out files with names matching ignore patterns
				if any(regex.fullmatch(filename) for regex in ignore_patterns):
					continue

				filename = Path(filename)
				if inclusive or filename.suffix[1:].lower() in formats:
					self.queue.append(ImageSet(dirpath / filename))

			dirscopy = dirnames.copy()
			dirnames.clear()

			for dirname in dirscopy:

				# filter out directories with names matching ignore patterns
				if any(regex.fullmatch(dirname) for regex in ignore_patterns):
					continue

				# if match:
				if any(regex.fullmatch(dirname) for regex in collection_patterns):
					self.queue.append(ImageSet(dirpath / dirname))
				elif recursive:
					dirnames.append(dirname)
				else:
					pass

	def add_history(self,
		kind   : Action,
		target : Optional[History] = None,
	) -> None:
		"""
		Add an action to the undo history.

		If there is already a following action, such as if the undo method has
		been called, replace the following action in the history rather than
		adding a new one.
		"""

		if self.history.next:
			self.history.next.kind = kind
			self.history.next.target = target
			self.history = self.history.next
		else:
			link = ActionQueue.History(kind, target)

			self.history.next = link
			link.prev = self.history
			self.history = link

	def clear_history(self) -> None:
		""" Clear the undo history """
		self.history = self.history_start
		self.history.next = None

	def skip(self) -> None:
		"""
		Remove the item in the front of the queue.

		Clears any active undo history.
		"""
		if self.__skip():
			self.add_history(ActionQueue.Action.SKIP)

	def delete(self) -> None:
		"""
		Remove the item in the front of the queue and mark its corresponding
		collection to be deleted upon a call to the apply method.

		Clears any active undo history.
		"""
		if self.__delete():
			self.add_history(ActionQueue.Action.DELETE)

	def select(self, destination : Path, overwrite : bool = False) -> None:
		"""
		Remove the item in the front of the queue and mark it to be moved to
		the provided destination upon a call to the apply method.

		Clears any active undo history.
		"""
		if self.__select(destination, overwrite):
			self.add_history(ActionQueue.Action.SELECT, destination)

	# def clone(self, destination, overwrite=False) -> None:
	# 	"""
	# 	Make a copy of the item in the front of the queue without removing ti
	# 	to be moved to the provided destination upon a call to the apply method.

	# 	This action cannot be undone.
	# 	"""

	def __skip(self) -> bool:
		""" Remove the front item from the queue and push it on the skip stack """
		if len(self.queue) != 0:
			self.skipped.append(self.queue.pop())
			return True
		return False

	def __back(self) -> bool:
		""" Pop the top item of the skip stack and place it at the front of the queue """
		if len(self.skipped) != 0:
			self.queue.append(self.skipped.pop())
			return True
		return False

	def __delete(self) -> bool:
		""" Remove the front item from the queue and push it on the delete stack """
		if len(self.queue) != 0:
			self.deleted.append(self.queue.pop())
			return True
		return False

	def __undelete(self) -> bool:
		""" Pop the top item of the delete stack and place it at the front of the queue """
		if len(self.deleted) != 0:
			self.queue.append(self.deleted.pop())
			return True
		return False

	def is_collision(self, destination : Path) -> bool:
		"""
		Return True if a call to select with the give destination would conflict
		with an existing file or a previously selected collection and False otherwise.
		"""
		# TODO figure out how to handle directories vs files
		return destination in self.selected or destination.exists()

	def resolve_collision_source(self, destination : Path) -> Path:
		return self.selected[destination][-1] if destination in self.selected else destination

	def __select(self, destination : Path, overwrite : bool = False) -> bool:
		"""
		Remove the front item from the queue and push it to the stack
		corresponding to the destination in the selected items dictionary.

		Return True if the select operation succeeded and False if it failed.

		If overwrite=False and the provided value for the destintion collides
		with an existing key, throws an ActionQueue.PathCollision exception.
		Otherwise, the new destination is pushed to the top of the relevant
		stack, overshadowing the previous value.
		"""
		if len(self.queue) != 0:
			
			# throw an exception if this action would overwrite an existing file
			# unless the caller specifically tells us that that's permissable
			if not overwrite and self.is_collision(destination):
				raise ActionQueue.PathCollision(
					"a file already exists at %s" % (destination)
				)

			# if we would overwrite one of our planned moves, move the file that would
			# be overwritten to the delete queue to keep things consistent
			if destination not in self.selected:
				self.selected[destination] = []

			self.selected[destination].append(self.queue.pop())
			return True
		return False

	def __unselect(self, destination : Path) -> bool:
		if destination in self.selected:
			stack = self.selected[destination]
			self.queue.append(stack.pop())
			if len(stack) == 0:
				self.selected.pop(destination)
			return True
		return False

	def requeue(self,
		criterion : Optional[str] = None,
		reverse   : bool          = False
	) -> None:
		self.clear_history()
		self.skipped.extend(self.queue)
		self.queue, self.skipped = self.skipped, self.queue
		self.skipped.clear()

		if criterion is not None:
			self.sort(criterion, reverse)

	def apply(self, delete_original : bool = False) -> None:

		# explicitly marked files are deleted regardless of mode
		for item in self.deleted:
			shutil.rmtree(item.path)
		self.deleted.clear()

		for destination, stack in self.selected.items():

			source = stack.pop()

			if destination.exists():# and destination.is_dir():
				# use this to remove collection folders that
				# should be overwritten rather than merged
				shutil.rmtree(destination)

			if delete_original:
				shutil.move(source.path, destination)

				# delete files with overwritten move locations
				for overwrite in stack:
					shutil.rmtree(overwrite)

			else:
				# copy2 only works on single files; copytree on directories
				if source.is_collection:
					shutil.copytree(source.path, destination)
				else:
					shutil.copy2(source.path, destination)

			stack.clear()

		self.selected.clear()
		self.clear_history()

class Handpix(object):

	IMAGE_PAGE = 0

	TEXT_PAGE  = 1

	@classmethod
	def cl_instance(cls, **kwargs):

		if "patterns" in kwargs:
			kwargs["patterns"] = [re.compile(regex) for regex in kwargs["patterns"]]

		if "ignore" in kwargs:
			kwargs["ignore"] = [re.compile(regex) for regex in kwargs["ignore"]]

		return Handpix(**kwargs)

	def __init__(self,
		destination     : str,
		sources         : List[str],
		threshold       : int              = 2,
		recursive       : bool             = False,
		inclusive       : bool             = False,
		verbose         : bool             = False,
		delete_original : bool             = False,
		patterns        : List[re.Pattern] = [],
		ignore          : List[re.Pattern] = [],
		sort            : str              = 'mtime',
		reverse         : bool             = True,
		recycle         : bool             = False,
	):

		self.image_size      = 500
		self.replace_preview = None

		# configuration options
		self.threshold       = threshold
		self.recursive       = recursive
		self.inclusive       = inclusive
		self.verbose         = verbose
		self.sort            = sort
		self.patterns        = patterns
		self.ignore          = ignore
		self.reverse         = reverse

		# number of sequential deletions
		self.kills = 0

		self.items = ActionQueue()

		for source in sources:
			self.items.add(
				path=source,
				recursive=self.recursive,
				inclusive=self.inclusive,
				collection_patterns=self.patterns,
				ignore_patterns=self.ignore,
			)

		self.items.sort(criterion=self.sort, reverse=self.reverse)

		# widget attribute definitions
		# builder       = Gtk.Builder.new_from_file("handpix.glade")
		builder       = Gtk.Builder.new_from_string(RESOURCES.GLADE_DATA, len(RESOURCES.GLADE_DATA))
		self.builder  = builder

		self.store    = Gtk.ListStore(str)

		def sort_func(model, a, b, userdata):
			x = model.get(a, 0)
			y = model.get(b, 0)
			return 1 if x > y else -1 if x < y else 0

		self.store.set_sort_column_id(0, Gtk.SortType.ASCENDING)
		self.store.set_sort_func(0, sort_func, None)

		self.treeview = builder.get_object("directory_treeview")
		self.treeview.set_model(self.store)

		self.column   = Gtk.TreeViewColumn("Destination", Gtk.CellRendererText(), text=0)
		self.treeview.append_column(self.column)

		self.toplevel = builder.get_object("toplevel")
		self.toplevel.connect("destroy", lambda widget: self.exit())
		self.toplevel.show_all()

		# settings widgets
		self.delete_original_checkbox = builder.get_object("delete_original_checkbox")
		self.recycle_queue_checkbox   = builder.get_object("recycle_queue_checkbox")
		self.settings_toggle_button   = builder.get_object("settings_toggle_button")
		self.settings_revealer        = builder.get_object("settings_revealer")
		self.delete_original          = delete_original
		self.recycle_queue            = recycle

		# viewer pane widgets
		self.set_name_entry   = builder.get_object("set_name_entry")
		self.new_folder_entry = builder.get_object("new_folder_entry")
		self.set_name_label   = builder.get_object("set_name_label")
		self.set_item_label   = builder.get_object("set_item_label")
		self.set_size_label   = builder.get_object("set_size_label")
		self.set_status_label = builder.get_object("set_status_label")
		self.progress_bar     = builder.get_object("progress_bar")

		self.preview_image    = builder.get_object("preview_image")
		self.preview_textarea = builder.get_object("preview_textarea")
		self.preview_notebook = builder.get_object("preview_notebook")

		# file overwrite confirmation mechanism
		self.confirm_popup   = builder.get_object("confirm_popup")
		self.confirm_confirm = builder.get_object("confirm_popup_confirm_button")
		self.confirm_cancel  = builder.get_object("confirm_popup_cancel_button")
		self.confirm_title   = builder.get_object("confirm_popup_title_label")
		self.confirm_message = builder.get_object("confirm_popup_message_label")
		
		self.confirm_popup.connect("response",
			lambda widget, event: self.confirm_popup.hide()
		)

		self.set_destination(Path(destination).expanduser())

		builder.connect_signals(HandpixCallbackHandler(self))

		self.refresh(exit_on_empty=False)

	delete_original = checkbox_property("delete_original_checkbox")
	recycle_queue   = checkbox_property("recycle_queue_checkbox")

	def settings_visible(self) -> bool:
		active = self.settings_toggle_button.get_active()
		self.settings_revealer.set_reveal_child(active)
		return active

	def set_destination(self, path: Path) -> None:
		"""
		Set the destination directory to the location of the provided path
		and load any subdirectories it contains into the side pane.
		"""
		self.destination = path
		self.store.clear()

		for child in path.iterdir():
			if child.is_dir():
				self.store.prepend([child.name])

	def refresh(self, exit_on_empty: bool = True) -> None:
		if len(self.items) == 0:

			# automatically loop queue if item avaiable and option set
			if self.recycle_queue and len(self.items.skipped) != 0:
				self.items.requeue(criterion=self.sort, reverse=self.reverse)
				self.refresh()
				return

			# update display to show empty
			self.preview_notebook.set_current_page(Handpix.IMAGE_PAGE)
			self.preview_image.set_from_pixbuf(ImageSet.DEFAULT_IMAGE)

			self.set_name_label.set_text("Queue is empty!")
			self.set_size_label.set_text("Size N/A")
			self.set_item_label.set_text("No file loaded.")
			self.set_status_label.set_text("end of queue")

			self.progress_bar.set_fraction(1.0)
			self.set_name_entry.set_text("")

			# if option is set, don't automatically prompt to apply
			if not exit_on_empty:
				return

			# prompt to apply changes and if changes applied prompt to contiue
			if not self.confirm("Apply changes?", "This action may modify the filesystem and cannot be undone."):
				return

			self.items.apply(self.delete_original)

			# for percentage in self.items.apply_iter(self.delete_original):
			# 	self.progress_bar.set_fraction(percentage)
			# 	print(percentage)

			if self.confirm("Changes applied! Continue?", "Skipped files will be requeued."):
				self.items.requeue(criterion=self.sort, reverse=self.reverse)
				self.refresh()
			else:
				self.exit()
		else:
			item          = self.items.peek()
			if not item: return

			kind = item.get_item_type()
			if   kind is ImageSet.Type.IMAGE:
				self.preview_notebook.set_current_page(Handpix.IMAGE_PAGE)
				self.preview_image.set_from_pixbuf(
					item.get_image(self.image_size)
				)
			elif kind is ImageSet.Type.TEXT:
				self.preview_notebook.set_current_page(Handpix.TEXT_PAGE)
				self.preview_textarea.get_buffer().set_text(
					item.get_text()
				)
			else:
				self.preview_notebook.set_current_page(Handpix.IMAGE_PAGE)
				self.preview_image.set_from_pixbuf(
					ImageSet.DEFAULT_IMAGE
				)

			self.set_name_label.set_text(item.get_item_name())
			self.set_size_label.set_text(item.humansize)
			self.set_item_label.set_text(item.get_progress_text())
			self.set_status_label.set_text(self.items.get_item_status())

			self.progress_bar.set_fraction(self.items.get_progress())

			parent, name  = item.pathparts()
			self.set_name_entry.set_text(name)

	def select(self) -> None:
		item = self.items.peek()
		if not item: return

		name = self.set_name_entry.get_text()

		model, tag = self.treeview.get_selection().get_selected()
		if tag is None:
			return

		center     = model.get_value(tag, 0)
		target     = self.destination / center / name

		confirmed  = False
		if self.items.is_collision(target):

			preview = self.items.resolve_collision_source(target)

			if self.replace_preview is None:
				self.replace_preview = ImageSet(preview)
			else:
				self.replace_preview.load_from(preview)

			self.set_name_label.set_text("Overwrite this set?")

			self.preview_image.set_from_pixbuf(
				self.replace_preview.get_image(self.image_size)
			)

			confirmed = self.confirm(
				title="Overwrite File?",
				message=str(target) + " will be overwritten",
			)

			if not confirmed:
				self.refresh()
				return

		self.items.select(target, overwrite=confirmed)

		self.kills = 0
		self.refresh()

	def skip(self) -> None:
		self.items.skip()
		self.kills = 0
		self.refresh()

	def delete(self) -> None:
		item = self.items.peek()
		if not item: return
		path = item.path

		if self.kills < self.threshold:
			confirmed = self.confirm(
				title="Delete File?",
				message=str(path) + " will be deleted"
			)

			if not confirmed:
				return

		self.items.delete()

		self.kills += 1
		self.refresh()

	def undo(self) -> None:
		self.items.undo()
		self.kills = 0
		self.refresh()

	def redo(self) -> None:
		self.items.redo()
		self.refresh()

	def next_in_set(self) -> None:
		if item := self.items.peek():
			item.next()
			self.refresh()

	def prev_in_set(self) -> None:
		if item := self.items.peek():
			item.prev()
			self.refresh()

	def confirm(self, title : str, message : str) -> bool:

		self.confirm_title.set_text(title)
		self.confirm_message.set_text(message)

		result = self.confirm_popup.run()

		if result == Gtk.ResponseType.DELETE_EVENT or result == Gtk.ResponseType.CANCEL:
			return False
		elif result == Gtk.ResponseType.OK:
			return True
		else:
			raise ValueError("got weird result: " + str(result))

	def new_folder(self) -> None:
		new_folder = self.destination / self.new_folder_entry.get_text()

		try:
			new_folder.mkdir()
			self.new_folder_entry.set_text("")
			self.set_destination(self.destination)
		except Exception as e:
			self.confirm("An error occured while trying to create this folder.", str(e))

	def reset_name_entry(self) -> None:
		item = self.items.peek()
		if not item: return

		parent, name = item.pathparts()
		self.set_name_entry.set_text(name)

	def zoom(self, offset: int) -> None:
		if  type(offset) is int and offset + self.image_size >= 0:
			self.image_size += offset
			self.refresh()
		elif type(offset) is float and offset != 0:
			self.image_size += offset * self.image_size
			self.refresh()

	def run(self) -> None:
		Gtk.main()

	def exit(self) -> None:
		Gtk.main_quit()

	def apply(self) -> bool:
		while self.confirm("Apply changes?", "This action may modify the filesystem and cannot be undone."):
			try:
				# for percentage in self.items.apply_iter(self.delete_original):
				# 	self.progress_bar.set_fraction(percentage)
				# 	print(percentage)
				self.items.apply(self.delete_original)
				self.refresh()
				return True
			except Exception as e:
				if self.confirm("An error occured while applying changes. Continue?", str(e)):
					continue
				break

		return False

class HandpixCallbackHandler(object):

	def __init__(self, application):
		self.application = application

	def on_skip_button_clicked(self, button):
		self.application.skip()

	def on_last_button_clicked(self, button):

		title    = "Really redo all previous actions?"
		subtitle = "Doing this may cause you to loose your position."

		if self.application.confirm(title, subtitle):

			while self.application.items.redo():
				pass

			self.application.refresh()

	def on_undo_button_clicked(self, button):
		self.application.undo()

	def on_redo_button_clicked(self, button):
		self.application.redo()

	def on_delete_button_clicked(self, button):
		self.application.delete()

	def on_select_button_clicked(self, button):
		self.application.select()

	def on_next_image_button_clicked(self, button):
		self.application.next_in_set()

	def on_prev_image_button_clicked(self, button):
		self.application.prev_in_set()

	def on_reload_destination_button_clicked(self, button):
		self.application.set_destination(
			self.application.destination
		)

	def on_zoom_in_button_clicked(self, button):
		self.application.zoom(+0.25)

	def on_zoom_out_button_clicked(self, button):
		self.application.zoom(-0.25)

	def on_new_folder_entry_activate(self, entry):
		self.application.new_folder()

	def on_new_folder_entry_icon_press(self, a, b, c):
		self.application.new_folder()

	def on_set_name_entry_icon_press(self, a, b, c):
		self.application.reset_name_entry()

	def on_apply_button_clicked(self, button):
		self.application.apply()

	def on_confirm_popup_confirm_button_clicked(self, button):
		self.application.confirm_popup.response(Gtk.ResponseType.OK)

	def on_confirm_popup_cancel_button_clicked(self, button):
		self.application.confirm_popup.response(Gtk.ResponseType.CANCEL)

	def on_directory_treeview_row_activated(self, a, b, c):
		self.application.select()

	def on_settings_toggle_button_toggled(self, button):
		self.application.settings_visible()
