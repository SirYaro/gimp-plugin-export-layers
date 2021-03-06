#
# This file is part of pygimplib.
#
# Copyright (C) 2014-2016 khalim19 <khalim19@gmail.com>
#
# pygimplib is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pygimplib is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pygimplib.  If not, see <http://www.gnu.org/licenses/>.
#

"""
This module defines:
* GTK overwrite dialog
* GTK progress updater
* GTK exception dialog
* GTK generic message dialog
* wrapper for `sys.excepthook` that displays the GTK exception dialog when an
  unhandled exception is raised
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

str = unicode

import functools
import os
import sys
import traceback

try:
  import webbrowser
except ImportError:
  _webbrowser_module_found = False
else:
  _webbrowser_module_found = True

import pygtk
pygtk.require("2.0")
import gtk
import gobject

import gimp
import gimpui

pdb = gimp.pdb

from . import overwrite
from . import progress

#===============================================================================


class GtkDialogOverwriteChooser(overwrite.InteractiveOverwriteChooser):
  
  """
  This class is used to display a GTK dialog prompt in an interactive environment
  when a file about to be saved has the same name as an already existing file.
  """
  
  _DIALOG_BORDER_WIDTH = 8
  _DIALOG_HBOX_CONTENTS_SPACING = 10
  _DIALOG_VBOX_SPACING = 5
  _DIALOG_ACTION_AREA_SPACING = 8
  
  def __init__(self, values_and_display_names, default_value, default_response, title="",
               parent=None, use_mnemonics=True):
    
    super(GtkDialogOverwriteChooser, self).__init__(values_and_display_names, default_value, default_response)
    
    self._title = title
    self._parent = parent
    self._use_mnemonics = use_mnemonics
    
    self._init_gui()
  
  def _init_gui(self):
    self._dialog = gimpui.Dialog(
      title="", role=None, parent=self._parent, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
    self._dialog.set_transient_for(self._parent)
    self._dialog.set_title(self._title)
    self._dialog.set_border_width(self._DIALOG_BORDER_WIDTH)
    self._dialog.set_resizable(False)
    
    self._dialog_icon = gtk.Image()
    self._dialog_icon.set_from_stock(gtk.STOCK_DIALOG_QUESTION, gtk.ICON_SIZE_DIALOG)
    
    self._dialog_text = gtk.Label("")
    self._dialog_text.set_line_wrap(True)
    self._dialog_text.set_use_markup(True)
    
    self._dialog_text_event_box = gtk.EventBox()
    self._dialog_text_event_box.add(self._dialog_text)
    
    self._hbox_dialog_contents = gtk.HBox(homogeneous=False)
    self._hbox_dialog_contents.set_spacing(self._DIALOG_HBOX_CONTENTS_SPACING)
    self._hbox_dialog_contents.pack_start(self._dialog_icon, expand=False, fill=False)
    self._hbox_dialog_contents.pack_start(self._dialog_text_event_box, expand=False, fill=False)
    
    if self._use_mnemonics:
      label_apply_to_all = _("_Apply action to all files")
    else:
      label_apply_to_all = _("Apply action to all files")
    self._checkbutton_apply_to_all = gtk.CheckButton(label=label_apply_to_all)
    self._checkbutton_apply_to_all.set_use_underline(self._use_mnemonics)
    
    self._dialog.vbox.set_spacing(self._DIALOG_VBOX_SPACING)
    self._dialog.vbox.pack_start(self._hbox_dialog_contents, expand=False, fill=False)
    self._dialog.vbox.pack_start(self._checkbutton_apply_to_all, expand=False, fill=False)
    
    self._buttons = {}
    for value, display_name in self.values_and_display_names:
      self._buttons[value] = self._dialog.add_button(display_name, value)
    
    self._dialog.action_area.set_spacing(self._DIALOG_ACTION_AREA_SPACING)
    
    self._checkbutton_apply_to_all.connect("toggled", self._on_apply_to_all_changed)
    
    self._is_dialog_text_allocated_size = False
    self._dialog_text_event_box.connect("size-allocate", self._on_dialog_text_event_box_size_allocate)
    
    self._dialog.set_focus(self._buttons[self.default_value])
  
  def _choose(self, filename):
    if filename is not None:
      filename_root, basename = os.path.split(filename)
      if filename_root:
        parent_directory = os.path.split(filename_root)[1]
        text_choose = (
          _("A file named \"{0}\" already exists in \"{1}\".").format(basename, parent_directory) + " ")
      else:
        text_choose = _("A file named \"{0}\" already exists.").format(basename) + "\n"
    else:
      text_choose = _("A file with the same name already exists.") + "\n"
    
    text_choose += _("What would you like to do?")
    
    self._dialog_text.set_markup(
      "<span font_size=\"large\"><b>" + gobject.markup_escape_text(text_choose) + "</b></span>")
    
    self._dialog.show_all()
    
    self._overwrite_mode = self._dialog.run()
    
    if self._overwrite_mode not in self._values:
      self._overwrite_mode = self.default_response
    
    self._dialog.hide()
    
    return self._overwrite_mode
  
  def _on_apply_to_all_changed(self, widget):
    self._is_apply_to_all = self._checkbutton_apply_to_all.get_active()
  
  def _on_dialog_text_event_box_size_allocate(self, dialog_text_event_box, allocation):
    if not self._is_dialog_text_allocated_size:
      self._is_dialog_text_allocated_size = True
      
      # Make sure the label uses as much width as it can in the dialog.
      dialog_text_allocation = dialog_text_event_box.get_allocation()
      dialog_vbox_allocation = self._dialog.vbox.get_allocation()
      self._dialog_text.set_size_request(dialog_vbox_allocation.width - dialog_text_allocation.x, -1)


#===============================================================================


def display_exception_message(exception_message, plugin_title=None, report_uri_list=None, parent=None):
  """
  Display an error message for exceptions unhandled by the plug-in.
  
  The message also displays the exception message in the Details box, which
  is collapsed by default.
  
  Optionally, the dialog can contain links to sites where the users can report
  this error, copying the exception message to better track the error down.
  
  Parameters:
  
  * `exception_message` - Exception message to display in the Details box.
  
  * `plugin_title` - Name of the plug-in (string) used as the message title and
    in the message contents.
  
  * `report_uri_list` - List of (name, URL) tuples where the user can report
    the error. If no report list is desired, pass None or an empty sequence.
  
  * `parent` - Parent GUI element.
  """
  
  dialog = gtk.MessageDialog(
    parent, type=gtk.MESSAGE_ERROR, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
  dialog.set_transient_for(parent)
  if plugin_title is not None:
    dialog.set_title(plugin_title)
  
  dialog.set_markup(
    "<span font_size=\"large\"><b>" + _("Oops. Something went wrong.") + "</b></span>")
  dialog.format_secondary_markup(
    _("{0} encountered an unexpected error and has to close. Sorry about that!").format(
      gobject.markup_escape_text(plugin_title)))
  
  expander = get_exception_details_expander(exception_message)
  expander.set_expanded(True)
  
  if report_uri_list:
    vbox_labels_report = get_report_link_buttons(
      report_uri_list, report_description=_(
        "You can help fix this error by sending a report with the text "
        "in the details above to one of the following sites"))
    dialog.vbox.pack_end(vbox_labels_report, expand=False, fill=False)
  
  dialog.vbox.pack_start(expander, expand=False, fill=False)
  
  dialog.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
  
  if expander.get_child() is not None:
    dialog.set_focus(expander.get_child())
  
  dialog.show_all()
  dialog.run()
  dialog.destroy()


def get_exception_details_expander(exception_message):
  expander = gtk.Expander()
  expander.set_use_markup(True)
  expander.set_label("<b>" + _("Details") + "</b>")
  
  scrolled_window = gtk.ScrolledWindow()
  scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
  scrolled_window.set_size_request(400, 200)
  scrolled_window.set_shadow_type(gtk.SHADOW_IN)
  
  exception_text_view = gtk.TextView()
  exception_text_view.set_editable(False)
  exception_text_view.set_wrap_mode(gtk.WRAP_WORD)
  exception_text_view.set_cursor_visible(False)
  exception_text_view.set_pixels_above_lines(1)
  exception_text_view.set_pixels_below_lines(1)
  exception_text_view.set_pixels_inside_wrap(0)
  exception_text_view.set_left_margin(5)
  exception_text_view.set_right_margin(5)
  exception_text_view.get_buffer().set_text(exception_message)
  
  scrolled_window.add(exception_text_view)
  expander.add(scrolled_window)
  
  return expander


def get_report_link_buttons(report_uri_list, report_description=None):
  if not report_uri_list:
    return None
  
  vbox_link_buttons = gtk.VBox(homogeneous=False)
  
  if report_description is not None:
    label_report_text = report_description
    if not _webbrowser_module_found:
      label_report_text += " " + _("(right-click to copy link)")
    label_report_text += ":"
    
    label_report = gtk.Label(label_report_text)
    label_report.set_alignment(0, 0.5)
    label_report.set_padding(3, 3)
    label_report.set_line_wrap(True)
    label_report.set_line_wrap_mode(gtk.WRAP_WORD)
    vbox_link_buttons.pack_start(label_report, expand=False, fill=False)
  
  report_linkbuttons = []
  for name, uri in report_uri_list:
    linkbutton = gtk.LinkButton(uri, label=name)
    linkbutton.set_alignment(0, 0.5)
    report_linkbuttons.append(linkbutton)
  
  for linkbutton in report_linkbuttons:
    vbox_link_buttons.pack_start(linkbutton, expand=False, fill=False)
  
  if _webbrowser_module_found:
    # Apparently, GTK doesn't know how to open URLs on Windows, hence the custom solution.
    for linkbutton in report_linkbuttons:
      linkbutton.connect("clicked", lambda linkbutton: webbrowser.open_new_tab(linkbutton.get_uri()))
  
  return vbox_link_buttons


def display_message(message, message_type, title=None, parent=None, buttons=gtk.BUTTONS_OK,
                    message_in_text_view=False, button_response_id_to_focus=None):
  """
  Display a generic message.
  
  Parameters:
  
  * `message` - The message to display.
  
  * `message_type` - GTK message type (gtk.MESSAGE_INFO, etc.).
  
  * `title` - Message title.
  
  * `parent` - Parent GUI element.
  
  * `buttons` - Buttons to display in the dialog.
  
  * `message_in_text_view` - If True, display text the after the first newline
    character in a text view.
  
  * `button_response_id_to_focus` - Response ID of the button to set as the
    focus. If None, the dialog determines which widget gets the focus.
  """
  
  dialog = gtk.MessageDialog(
    parent=parent, type=message_type, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=buttons)
  dialog.set_transient_for(parent)
  if title is not None:
    dialog.set_title(title)
  
  messages = message.split("\n", 1)
  if len(messages) > 1:
    dialog.set_markup(gobject.markup_escape_text(messages[0]))
    
    if message_in_text_view:
      text_view = gtk.TextView()
      text_view.set_editable(False)
      text_view.set_wrap_mode(gtk.WRAP_WORD)
      text_view.set_cursor_visible(False)
      text_view.set_pixels_above_lines(1)
      text_view.set_pixels_below_lines(1)
      text_view.set_pixels_inside_wrap(0)
      text_view.get_buffer().set_text(messages[1])
      
      scrolled_window = gtk.ScrolledWindow()
      scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
      scrolled_window.set_size_request(-1, 100)
      scrolled_window.set_shadow_type(gtk.SHADOW_IN)
      
      scrolled_window.add(text_view)
      
      vbox = dialog.get_message_area()
      vbox.pack_end(scrolled_window, expand=True, fill=True)
    else:
      dialog.format_secondary_markup(gobject.markup_escape_text(messages[1]))
  else:
    dialog.set_markup(gobject.markup_escape_text(message))
  
  if button_response_id_to_focus is not None:
    button = dialog.get_widget_for_response(button_response_id_to_focus)
    if button is not None:
      dialog.set_focus(button)
  
  dialog.show_all()
  response_id = dialog.run()
  dialog.destroy()
  
  return response_id


#===============================================================================


_gui_excepthook_parent = None


def set_gui_excepthook(plugin_title, report_uri_list=None, parent=None):
  """
  Modify `sys.excepthook` to display an error dialog for unhandled exceptions.
  
  Don't display the dialog for exceptions which are not subclasses of
  `Exception` (such as `SystemExit or `KeyboardInterrupt`).
  
  Parameters:
  
  * `plugin_title` - Name of the plug-in (string) used as the dialog title and
    in the dialog contents.
  
  * `report_uri_list` - List of (name, URL) tuples where the user can report
    the error. If no report list is desired, pass None or an empty sequence.
  
  * `parent` - Parent GUI element.
  """
  
  global _gui_excepthook_parent
  
  _gui_excepthook_parent = parent
  
  def real_decorator(func):
    
    @functools.wraps(func)
    def func_wrapper(self, *args, **kwargs):
      
      def gui_excepthook(exc_type, exc_value, exc_traceback):
        orig_sys_excepthook(exc_type, exc_value, exc_traceback)
        
        if issubclass(exc_type, Exception):
          exception_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
          display_exception_message(
            exception_message, plugin_title=plugin_title, report_uri_list=report_uri_list,
            parent=_gui_excepthook_parent)
          # Make sure to quit the application since unhandled exceptions can
          # mess up the application state.
          if gtk.main_level() > 0:
            gtk.main_quit()
      
      orig_sys_excepthook = sys.excepthook
      sys.excepthook = gui_excepthook
      
      func(self, *args, **kwargs)
      
      sys.excepthook = orig_sys_excepthook
  
    return func_wrapper
  
  return real_decorator


def set_gui_excepthook_parent(parent):
  """
  Set the parent GUI element to attach the exception dialog to when using
  `set_gui_excepthook`. This function allows to modify the parent dynamically
  even after decorating a function with `set_gui_excepthook`.
  """
  
  global _gui_excepthook_parent
  
  _gui_excepthook_parent = parent


#===============================================================================


class GtkProgressUpdater(progress.ProgressUpdater):
  
  def _fill_progress_bar(self):
    self.progress_bar.set_fraction(self._num_finished_tasks / self.num_total_tasks)
    self._force_update()
  
  def _set_text_progress_bar(self, text):
    self.progress_bar.set_text(text)
    self._force_update()
  
  def _force_update(self):
    # This is necessary for the GTK progress bar to be updated properly.
    # See http://faq.pygtk.org/index.py?req=show&file=faq23.020.htp
    while gtk.events_pending():
      gtk.main_iteration()
