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
This module tests the `pgitemtree` module.

Because the public interface to test is identical for all `ItemTree` subclasses,
it is sufficient to test `pgitemtree` using one of the subclasses. `LayerTree`
was chosen for this purpose.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

str = unicode

import collections
import os
import unittest

try:
  import cPickle as pickle
except ImportError:
  import pickle

from ..lib import mock

from . import gimpstubs
from .. import pgitemtree

#===============================================================================

LIB_NAME = ".".join(__name__.split(".")[:-2])

#===============================================================================


class LayerFilterRules(object):
  
  @staticmethod
  def is_layer(layer_elem):
    return layer_elem.item_type == layer_elem.ITEM
  
  @staticmethod
  def is_layer_or_empty_group(layer_elem):
    return layer_elem.item_type in (layer_elem.ITEM, layer_elem.EMPTY_GROUP)
  
  @staticmethod
  def is_path_visible(layer_elem):
    return layer_elem.path_visible
  
  @staticmethod
  def has_matching_file_extension(layer_elem, file_extension):
    return layer_elem.name.endswith("." + file_extension)


#===============================================================================


def _parse_layers(layer_tree_string):
  """
  From a given string containing layer names separated by lines and
  curly braces (each on a separate line), return an image containing parsed
  layers.
  
  Leading or trailing spaces in each line in the string are truncated.
  """
  
  image = gimpstubs.ImageStub()
  
  layer_tree_string = layer_tree_string.strip()
  lines = layer_tree_string.splitlines(False)
  
  num_lines = len(lines)
  parents = [image]
  current_parent = image
  
  for i in range(num_lines):
    current_symbol = lines[i].strip()
    
    layer = None
    
    if current_symbol.endswith(" {"):
      layer = gimpstubs.LayerGroupStub(current_symbol.rstrip(" {"))
      current_parent.layers.append(layer)
      current_parent = layer
      parents.append(current_parent)
    elif current_symbol == "}":
      parents.pop()
      current_parent = parents[-1]
    else:
      layer = gimpstubs.LayerStub(current_symbol)
      current_parent.layers.append(layer)
    
    if layer is not None:
      layer.parent = current_parent
  
  return image


#===============================================================================


@mock.patch(LIB_NAME + ".pgitemtree.pdb", new=gimpstubs.PdbStub())
@mock.patch(LIB_NAME + ".pgitemtree.gimp.GroupLayer", new=gimpstubs.LayerGroupStub)
class TestLayerTree(unittest.TestCase):

  @mock.patch(LIB_NAME + ".pgitemtree.pdb", new=gimpstubs.PdbStub())
  @mock.patch(LIB_NAME + ".pgitemtree.gimp.GroupLayer", new=gimpstubs.LayerGroupStub)
  def setUp(self):
    layers_string = """
      Corners {
        top-left-corner
        top-right-corner
        top-left-corner: {
        }
        top-left-corner:: {
          bottom-right-corner
          bottom-right-corner:
          bottom-left-corner
        }
      }
      Corners: {
        top-left-corner:::
      }
      Frames {
        top-frame
      }
      main-background.jpg
      main-background.jpg:
      Overlay {
      }
      Corners::
      top-left-corner::::
      main-background.jpg:: {
        alt-frames
        alt-corners
      }
    """
    
    image = _parse_layers(layers_string)
    self.layer_tree = pgitemtree.LayerTree(image)
  
  def test_get_orig_name_get_parents_get_children(self):
    layer_elem_tree = collections.OrderedDict([
      ("Corners", [[], ["top-left-corner", "top-right-corner", "top-left-corner:", "top-left-corner::"]]),
      ("top-left-corner", [["Corners"], None]),
      ("top-right-corner", [["Corners"], None]),
      ("top-left-corner:", [["Corners"], []]),
      ("top-left-corner::", [["Corners"], ["bottom-right-corner", "bottom-right-corner:", "bottom-left-corner"]]),
      ("bottom-right-corner", [["Corners", "top-left-corner::"], None]),
      ("bottom-right-corner:", [["Corners", "top-left-corner::"], None]),
      ("bottom-left-corner", [["Corners", "top-left-corner::"], None]),
      ("Corners:", [[], ["top-left-corner:::"]]),
      ("top-left-corner:::", [["Corners:"], None]),
      ("Frames", [[], ["top-frame"]]),
      ("top-frame", [["Frames"], None]),
      ("main-background.jpg", [[], None]),
      ("main-background.jpg:", [[], None]),
      ("Overlay", [[], []]),
      ("Corners::", [[], None]),
      ("top-left-corner::::", [[], None]),
      ("main-background.jpg::", [[], ["alt-frames", "alt-corners"]]),
      ("alt-frames", [["main-background.jpg::"], None]),
      ("alt-corners", [["main-background.jpg::"], None]),
    ])
    
    for layer_elem, orig_name in zip(self.layer_tree, layer_elem_tree.keys()):
      self.assertEqual(layer_elem.orig_name, orig_name)
    
    for layer_elem, parents_and_children in zip(self.layer_tree, layer_elem_tree.values()):
      parents = parents_and_children[0]
      children = parents_and_children[1]
      
      self.assertListEqual([parent.orig_name for parent in layer_elem.parents], parents)
      
      if children is not None:
        self.assertListEqual([child.orig_name for child in layer_elem.children], children)
      else:
        self.assertIsNone(layer_elem.children)
  
  def test_get_len(self):
    layer_count_total = 20
    layer_count_only_layers = 13
    
    self.assertEqual(len(self.layer_tree), layer_count_total)
    
    self.layer_tree.is_filtered = True
    self.layer_tree.filter.add_rule(LayerFilterRules.is_layer)
    
    self.assertEqual(len(self.layer_tree), layer_count_only_layers)
  
  def test_get_filepath(self):
    output_directory = os.path.join("D:", os.sep, "testgimp")
    
    # `layer_elem` with parents
    layer_elem = self.layer_tree['bottom-right-corner']
    
    self.assertEqual(
      layer_elem.get_filepath(output_directory),
      os.path.join(output_directory, "Corners", "top-left-corner::", layer_elem.name))
    self.assertEqual(
      layer_elem.get_filepath(output_directory, include_item_path=False),
      os.path.join(output_directory, layer_elem.name))
    self.assertEqual(
      layer_elem.get_filepath("testgimp"),
      os.path.join(os.getcwd(), "testgimp", "Corners", "top-left-corner::", layer_elem.name))
    self.assertEqual(
      layer_elem.get_filepath(None),
      os.path.join(os.getcwd(), "Corners", "top-left-corner::", layer_elem.name))
    
    itemtree_empty_layer_group = self.layer_tree['top-left-corner:']
    
    self.assertEqual(
      itemtree_empty_layer_group.get_filepath(output_directory),
      os.path.join(output_directory, "Corners", itemtree_empty_layer_group.name))
    self.assertEqual(
      itemtree_empty_layer_group.get_filepath(output_directory, include_item_path=False),
      os.path.join(output_directory, itemtree_empty_layer_group.name))
    
    itemtree_empty_layer_group_no_parents = self.layer_tree['Overlay']
    
    self.assertEqual(
      itemtree_empty_layer_group_no_parents.get_filepath(output_directory),
      os.path.join(output_directory, itemtree_empty_layer_group_no_parents.name))
    self.assertEqual(
      itemtree_empty_layer_group_no_parents.get_filepath(output_directory),
      itemtree_empty_layer_group_no_parents.get_filepath(output_directory, include_item_path=False))
  
  #-----------------------------------------------------------------------------
    
  def _compare_uniquified_without_parents(self, layer_tree, uniquified_names):
    for key, name in uniquified_names.items():
      self.assertEqual(
        layer_tree[key].name, name,
        "'" + key + "': '" + str(layer_tree[key].name) + "' != '" + str(name) + "'")
  
  def _compare_uniquified_with_parents(self, item_tree, uniquified_names):
    for key, item_path in uniquified_names.items():
      path_components, name = item_path[:-1], item_path[-1]
      self.assertEqual(
        item_tree[key].get_path_components(), path_components,
        ("parents: '" + key + "': '" + str(item_tree[key].get_path_components())
         + "' != '" + str(path_components) + "'"))
      self.assertEqual(
        item_tree[key].name, name,
        ("layer name: '" + key + "': '" + str(item_tree[key].name)
         + "' != '" + str(name) + "'"))
  
  def test_uniquify_without_layer_groups(self):
    uniquified_names = collections.OrderedDict([
      ("top-left-corner", "top-left-corner"),
      ("top-right-corner", "top-right-corner"),
      ("top-left-corner:", "top-left-corner (1)"),
      ("bottom-right-corner", "bottom-right-corner"),
      ("bottom-right-corner:", "bottom-right-corner (1)"),
      ("bottom-left-corner", "bottom-left-corner"),
      ("top-left-corner:::", "top-left-corner (2)"),
      ("top-frame", "top-frame"),
      ("main-background.jpg", "main-background.jpg"),
      ("main-background.jpg:", "main-background.jpg (1)"),
      ("Corners", "Corners"),
      ("top-left-corner::::", "top-left-corner (3)")
    ])
    
    # This is to make the uniquification work properly for these tests. It's not
    # inside the `uniquify_names` method because the code that uses this
    # method may need to uniquify non-empty layer groups in some scenarios
    # (such as when merging non-empty layer groups into layers, which would not
    # match the filter).
    self.layer_tree.is_filtered = True
    self.layer_tree.filter.add_rule(LayerFilterRules.is_layer_or_empty_group)
    
    for layer_elem in self.layer_tree:
      self.layer_tree.validate_name(layer_elem)
      self.layer_tree.uniquify_name(layer_elem, include_item_path=False)
    self._compare_uniquified_without_parents(self.layer_tree, uniquified_names)
  
  def test_uniquify_with_layer_groups(self):
    uniquified_names = collections.OrderedDict([
      ("Corners", ["Corners"]),
      ("top-left-corner", ["Corners", "top-left-corner"]),
      ("top-right-corner", ["Corners", "top-right-corner"]),
      ("top-left-corner:", ["Corners", "top-left-corner (1)"]),
      ("top-left-corner::", ["Corners", "top-left-corner (2)"]),
      ("bottom-right-corner", ["Corners", "top-left-corner (2)", "bottom-right-corner"]),
      ("bottom-right-corner:", ["Corners", "top-left-corner (2)", "bottom-right-corner (1)"]),
      ("bottom-left-corner", ["Corners", "top-left-corner (2)", "bottom-left-corner"]),
      ("Corners:", ["Corners (1)"]),
      ("top-left-corner:::", ["Corners (1)", "top-left-corner"]),
      ("Frames", ["Frames"]),
      ("top-frame", ["Frames", "top-frame"]),
      ("main-background.jpg", ["main-background.jpg"]),
      ("main-background.jpg:", ["main-background.jpg (1)"]),
      ("Corners::", ["Corners (2)"]),
      ("top-left-corner::::", ["top-left-corner"]),
      ("main-background.jpg::", ["main-background.jpg (2)"]),
      ("alt-frames", ["main-background.jpg (2)", "alt-frames"]),
      ("alt-corners", ["main-background.jpg (2)", "alt-corners"]),
    ])
    
    self.layer_tree.is_filtered = True
    self.layer_tree.filter.add_rule(LayerFilterRules.is_layer_or_empty_group)
    
    for layer_elem in self.layer_tree:
      self.layer_tree.validate_name(layer_elem)
      self.layer_tree.uniquify_name(layer_elem, include_item_path=True)
    self._compare_uniquified_with_parents(self.layer_tree, uniquified_names)
  
  def test_uniquify_with_regards_to_file_extension(self):
    def _get_file_extension_start_position(str_):
      position = str_.rfind(".")
      if position == -1:
        position = len(str_)
      return position
    
    uniquified_names = collections.OrderedDict([
      ("main-background.jpg", ["main-background.jpg"]),
      ("main-background.jpg:", ["main-background (1).jpg"]),
      ("main-background.jpg::", ["main-background.jpg (1)"])
    ])
    
    self.layer_tree.is_filtered = True
    self.layer_tree.filter.add_rule(LayerFilterRules.is_layer_or_empty_group)
    
    for layer_elem in self.layer_tree:
      self.layer_tree.validate_name(layer_elem)
      self.layer_tree.uniquify_name(
        layer_elem, include_item_path=True,
        uniquifier_position=_get_file_extension_start_position(layer_elem.name))
    self._compare_uniquified_with_parents(self.layer_tree, uniquified_names)
  
  def test_reset_name(self):
    self.layer_tree['Corners'].name = "Corners.png"
    
    self.layer_tree.validate_name(self.layer_tree['Corners'])
    self.layer_tree.uniquify_name(self.layer_tree['Corners'])
    
    self.layer_tree.validate_name(self.layer_tree['Corners::'])
    self.layer_tree.uniquify_name(self.layer_tree['Corners::'])
    
    self.layer_tree.reset_name(self.layer_tree['Corners'])
    
    self.layer_tree.validate_name(self.layer_tree['Corners'])
    self.layer_tree.uniquify_name(self.layer_tree['Corners'])
    
    self.assertEqual(self.layer_tree['Corners::'].name, "Corners")
    self.assertEqual(self.layer_tree['Corners'].name, "Corners (1)")
  
  def test_reset_item_elements(self):
    self.layer_tree['Corners'].name = "Corners.png"
    self.layer_tree['Corners:'].name = "Corners.png:"
    
    self.layer_tree.validate_name(self.layer_tree['Corners'])
    self.layer_tree.uniquify_name(self.layer_tree['Corners'])
    self.layer_tree.validate_name(self.layer_tree['Corners:'])
    self.layer_tree.uniquify_name(self.layer_tree['Corners:'])
    
    self.layer_tree.reset_item_elements()
    
    self.assertEqual(self.layer_tree['Corners'].name, "Corners")
    self.assertEqual(self.layer_tree['Corners:'].name, "Corners:")


@mock.patch(LIB_NAME + ".pgitemtree.pdb", new=gimpstubs.PdbStub())
class TestLayerTreeElement(unittest.TestCase):
  
  @mock.patch(LIB_NAME + ".pgitemtree.pdb", new=gimpstubs.PdbStub())
  def setUp(self):
    self.layer_elem = pgitemtree._ItemTreeElement(gimpstubs.LayerStub("main-background.jpg"))
  
  def test_str(self):
    self.assertEqual(str(self.layer_elem), "<_ItemTreeElement 'main-background.jpg'>")
  
  def test_get_file_extension(self):
    self.assertEqual(self.layer_elem.get_file_extension(), "jpg")
    
    self.layer_elem.name = ".jpg"
    self.assertEqual(self.layer_elem.get_file_extension(), "jpg")
  
  def test_get_file_extension_no_extension(self):
    self.layer_elem.name = "main-background"
    self.assertEqual(self.layer_elem.get_file_extension(), "")
    
    self.layer_elem.name = "main-background."
    self.assertEqual(self.layer_elem.get_file_extension(), "")
    
    self.layer_elem.name = "."
    self.assertEqual(self.layer_elem.get_file_extension(), "")
  
  def test_get_file_extension_unrecognized_extension(self):
    self.layer_elem.name = "main-background.aaa"
    self.assertEqual(self.layer_elem.get_file_extension(), "aaa")
    
    self.layer_elem.name = ".aaa"
    self.assertEqual(self.layer_elem.get_file_extension(), "aaa")
  
  def test_get_file_extension_multiple_periods(self):
    self.layer_elem.name = "main-background.xcf.bz2"
    self.assertEqual(self.layer_elem.get_file_extension(), "xcf.bz2")
  
  def test_get_file_extension_multiple_periods_unrecognized_extension(self):
    self.layer_elem.name = "main-background.aaa.bbb"
    self.assertEqual(self.layer_elem.get_file_extension(), "bbb")
  
  def test_set_file_extension(self):
    self.layer_elem.set_file_extension("png")
    self.assertEqual(self.layer_elem.name, "main-background.png")
    
    self.layer_elem.name = "main-background.jpg"
    self.layer_elem.set_file_extension(".png")
    self.assertEqual(self.layer_elem.name, "main-background.png")
    
    self.layer_elem.name = "main-background."
    self.layer_elem.set_file_extension("png")
    self.assertEqual(self.layer_elem.name, "main-background.png")
  
  def test_set_file_extension_turn_uppercase_to_lowercase(self):
    self.layer_elem.set_file_extension("PNG")
    self.assertEqual(self.layer_elem.name, "main-background.png")
  
  def test_set_file_extension_no_extension(self):
    self.layer_elem.set_file_extension(None)
    self.assertEqual(self.layer_elem.name, "main-background")
    
    self.layer_elem.name = "main-background.jpg"
    self.layer_elem.set_file_extension(".")
    self.assertEqual(self.layer_elem.name, "main-background")
  
  def test_set_file_extension_from_multiple_periods(self):
    self.layer_elem.name = "main-background.xcf.bz2"
    self.layer_elem.set_file_extension("png")
    self.assertEqual(self.layer_elem.name, "main-background.png")
  
  def test_set_file_extension_from_single_period_within_multiple_periods(self):
    self.layer_elem.name = "main-background.aaa.jpg"
    self.layer_elem.set_file_extension("png")
    self.assertEqual(self.layer_elem.name, "main-background.aaa.png")
  
  def test_set_file_extension_multiple_consecutive_periods(self):
    self.layer_elem.name = "main-background..jpg"
    self.layer_elem.set_file_extension("png")
    self.assertEqual(self.layer_elem.name, "main-background..png")
  
  def test_get_base_name(self):
    self.layer_elem.name = "main-background"
    self.assertEqual(self.layer_elem.get_base_name(), "main-background")
    self.layer_elem.name = "main-background."
    self.assertEqual(self.layer_elem.get_base_name(), "main-background.")
    self.layer_elem.name = "main-background.jpg"
    self.assertEqual(self.layer_elem.get_base_name(), "main-background")
    self.layer_elem.name = "main-background..jpg"
    self.assertEqual(self.layer_elem.get_base_name(), "main-background.")
    self.layer_elem.name = "..jpg"
    self.assertEqual(self.layer_elem.get_base_name(), ".")
    self.layer_elem.name = ".jpg"
    self.assertEqual(self.layer_elem.get_base_name(), "")
    self.layer_elem.name = "."
    self.assertEqual(self.layer_elem.get_base_name(), ".")
  
  @mock.patch(LIB_NAME + ".pgitemtree.gimp", new=gimpstubs.GimpModuleStub())
  def test_add_tag(self):
    self.assertEqual(self.layer_elem.tags, set())
    
    self.layer_elem.add_tag("background")
    self.assertIn("background", self.layer_elem.tags)
    
    self.layer_elem.add_tag("foreground")
    self.assertIn("background", self.layer_elem.tags)
    self.assertIn("foreground", self.layer_elem.tags)
  
  @mock.patch(LIB_NAME + ".pgitemtree.gimp", new=gimpstubs.GimpModuleStub())
  def test_remove_tag(self):
    self.assertEqual(self.layer_elem.tags, set())
    
    with self.assertRaises(ValueError):
      self.layer_elem.remove_tag("background")
    
    self.layer_elem.add_tag("background")
    self.layer_elem.remove_tag("background")
    self.assertNotIn("background", self.layer_elem.tags)
  
  @mock.patch(LIB_NAME + ".pgitemtree.gimp", new=gimpstubs.GimpModuleStub())
  def test_initial_tags(self):
    layer_elem_tags_source_name = "test"
    
    layer = gimpstubs.LayerStub("layer")
    layer.parasite_attach(gimpstubs.ParasiteStub(layer_elem_tags_source_name, 0, pickle.dumps(set(["background"]))))
    
    layer_elem = pgitemtree._ItemTreeElement(layer, tags_source_name=layer_elem_tags_source_name)
    self.assertIn("background", layer_elem.tags)
