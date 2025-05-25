import unittest
from unittest.mock import Mock, patch, MagicMock
import os # For os.path.join, os.path.splitext if used directly
from datetime import datetime

# Attempt to import ImageViewer, may need to adjust sys.path if running test directly
# and image_viewer.py is not in the same directory or Python path.
try:
    from image_viewer import ImageViewer
except ImportError:
    # This is a fallback for environments where the path might not be set up.
    import sys
    # Ensure image_viewer.py is in the path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from image_viewer import ImageViewer


class TestImageViewerLogic(unittest.TestCase):

    def setUp(self):
        """Set up for each test method."""
        # Mock the Tkinter root window
        self.mock_root = MagicMock()
        self.mock_root.winfo_width.return_value = 800 # Default root window size
        self.mock_root.winfo_height.return_value = 600

        # Patch the Canvas and other Tkinter UI elements that ImageViewer creates internally
        with patch('image_viewer.Canvas', MagicMock()) as self.mock_canvas_constructor, \
             patch('image_viewer.Menu', MagicMock()):
            self.viewer = ImageViewer(self.mock_root)
            self.viewer.canvas = self.mock_canvas_constructor.return_value

        # Set default canvas dimensions for tests
        self.viewer.canvas.winfo_width.return_value = 600
        self.viewer.canvas.winfo_height.return_value = 400

        # Mock the original Pillow image object
        self.mock_pil_image = MagicMock(spec=Image.Image) # Use spec for better mocking
        self.mock_pil_image.width = 1000
        self.mock_pil_image.height = 750
        self.mock_pil_image.size = (self.mock_pil_image.width, self.mock_pil_image.height)
        
        # Assign this mock image to the viewer instance
        self.viewer.image = self.mock_pil_image
        self.viewer.image_path = "/fake/path/to/original_image.png" # Default image path
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 0
        self.viewer.image_y = 0
        
        # Mock PhotoImage
        self.mock_photo_image_patch = patch('image_viewer.ImageTk.PhotoImage', MagicMock())
        self.mock_photo_image_constructor = self.mock_photo_image_patch.start()
        self.addCleanup(self.mock_photo_image_patch.stop)

        # Mock messagebox
        self.mock_messagebox_patch = patch('image_viewer.messagebox', MagicMock())
        self.mock_messagebox = self.mock_messagebox_patch.start()
        self.addCleanup(self.mock_messagebox_patch.stop)
        
        # Ensure PIL_AVAILABLE is True for these tests
        self.pil_available_patch = patch('image_viewer.PIL_AVAILABLE', True)
        self.pil_available_patch.start()
        self.addCleanup(self.pil_available_patch.stop)


    def test_initial_state_after_setup(self):
        """Test that the viewer is in the expected state after setUp."""
        self.assertEqual(self.viewer.zoom_factor, 1.0)
        self.assertEqual(self.viewer.image_x, 0)
        self.assertEqual(self.viewer.image_y, 0)
        self.assertIsNotNone(self.viewer.image)
        self.assertEqual(self.viewer.image.width, 1000)
        self.assertEqual(self.viewer.image.height, 750)
        self.assertEqual(self.viewer.image_path, "/fake/path/to/original_image.png")

    # --- Zoom Logic Tests ---
    def create_mock_event(self, x, y, delta=0, num=0):
        """Helper to create a mock event object for zoom/pan tests."""
        event = Mock()
        event.x = x
        event.y = y
        event.delta = delta
        event.num = num
        return event

    def test_zoom_in(self):
        """Test basic zoom-in functionality."""
        initial_zoom = self.viewer.zoom_factor
        mock_event = self.create_mock_event(x=100, y=100, delta=120) # Windows scroll up
        self.viewer.zoom_image(mock_event)
        self.assertGreater(self.viewer.zoom_factor, initial_zoom)

    def test_zoom_out(self):
        """Test basic zoom-out functionality."""
        initial_zoom = self.viewer.zoom_factor
        mock_event = self.create_mock_event(x=100, y=100, delta=-120) # Windows scroll down
        self.viewer.zoom_image(mock_event)
        self.assertLess(self.viewer.zoom_factor, initial_zoom)

    def test_zoom_limits(self):
        """Test that zoom factor is clamped to min/max limits."""
        # Zoom in excessively
        for _ in range(50):
            self.viewer.zoom_image(self.create_mock_event(100, 100, delta=120))
        self.assertAlmostEqual(self.viewer.zoom_factor, 5.0, places=5)

        # Reset zoom for next part of test (not strictly necessary if always starting from 1.0 in setup)
        self.viewer.zoom_factor = 1.0 
        self.viewer.image_x = 0 # Reset position as zoom changes it
        self.viewer.image_y = 0

        # Zoom out excessively
        for _ in range(50):
            self.viewer.zoom_image(self.create_mock_event(100, 100, delta=-120))
        self.assertAlmostEqual(self.viewer.zoom_factor, 0.1, places=5)
        
    def test_zoom_towards_cursor_calculation(self):
        """
        Test the core logic of zooming towards the cursor.
        If we zoom in on a point, that point on the original image
        should remain under the cursor.
        """
        self.viewer.image = self.mock_pil_image # Original image 1000x750
        self.viewer.zoom_factor = 1.0
        # Initial state: image top-left is at canvas (0,0)
        self.viewer.image_x = 0 
        self.viewer.image_y = 0
        
        # Cursor position on canvas
        mouse_x_on_canvas = 100
        mouse_y_on_canvas = 75

        # The point on the original image under the cursor is (100, 75)
        # because zoom is 1.0 and image_x/y is 0.
        
        mock_event = self.create_mock_event(mouse_x_on_canvas, mouse_y_on_canvas, delta=120) # Zoom in
        
        # Store previous zoom_factor, as it's used in the calculation within zoom_image
        # The actual method `zoom_image` uses self.zoom_factor before it's updated.
        # So the `previous_zoom_factor` for the first zoom step is self.zoom_factor.
        # Our mock setup needs to reflect that `img_coord_x_on_original` uses the `previous_zoom_factor`.
        # The `zoom_image` method calculates `previous_zoom_factor` internally.
        # The calculation in the method is:
        # img_coord_x_on_original = (mouse_x - self.image_x) / previous_zoom_factor (where previous_zoom_factor is self.zoom_factor before update)
        # self.image_x = mouse_x - (img_coord_x_on_original * self.zoom_factor) (where self.zoom_factor is the new one)

        self.viewer.zoom_image(mock_event) # This updates self.zoom_factor and self.image_x/y

        new_zoom_factor = self.viewer.zoom_factor # Should be 1.0 * 1.1 = 1.1
        
        # Verify the new image_x and image_y
        # Expected original image point under cursor: (100, 75)
        # new_image_x = mouse_x_on_canvas - (100 * new_zoom_factor)
        # new_image_y = mouse_y_on_canvas - (75 * new_zoom_factor)
        expected_image_x = mouse_x_on_canvas - (100 * new_zoom_factor)
        expected_image_y = mouse_y_on_canvas - (75 * new_zoom_factor)
        
        self.assertAlmostEqual(self.viewer.image_x, expected_image_x, places=5)
        self.assertAlmostEqual(self.viewer.image_y, expected_image_y, places=5)

        # After zoom, the point (100,75) on the original image should still be under the cursor (100,75) on canvas.
        # Check: (mouse_x_on_canvas - new_image_x) / new_zoom_factor should be 100
        # Check: (mouse_y_on_canvas - new_image_y) / new_zoom_factor should be 75
        self.assertAlmostEqual((mouse_x_on_canvas - self.viewer.image_x) / self.viewer.zoom_factor, 100, places=3)
        self.assertAlmostEqual((mouse_y_on_canvas - self.viewer.image_y) / self.viewer.zoom_factor, 75, places=3)


    # --- Crop Coordinate Calculation Tests (`save_cropped_image`) ---

    def set_canvas_dimensions(self, width, height):
        self.viewer.canvas.winfo_width.return_value = width
        self.viewer.canvas.winfo_height.return_value = height

    @patch('image_viewer.os.path')
    @patch('image_viewer.datetime')
    def common_crop_save_test_logic(self, mock_dt, mock_os_path, 
                                    original_path, expected_crop_box, 
                                    fixed_timestamp_str="20230101103000"):
        """
        Refactored helper for testing save_cropped_image.
        Mocks datetime and os.path, calls save_cropped_image, 
        and asserts the crop box and save path.
        """
        # Setup mocks for datetime and os.path
        mock_dt.now.return_value = datetime(2023, 1, 1, 10, 30, 0) # Corresponds to fixed_timestamp_str
        
        self.viewer.image_path = original_path
        
        # Configure os.path mocks - these need to be somewhat dynamic based on original_path
        mock_os_path.dirname.return_value = os.path.dirname(original_path)
        mock_os_path.basename.return_value = os.path.basename(original_path)
        # Let splitext and join use their real implementations for simplicity and correctness
        mock_os_path.splitext.side_effect = os.path.splitext
        mock_os_path.join.side_effect = os.path.join

        # Mock the image's crop and save methods
        mock_cropped_image = MagicMock()
        self.viewer.image.crop.return_value = mock_cropped_image
        
        self.viewer.save_cropped_image() # Call the method

        # Assert crop was called with the correct box
        self.viewer.image.crop.assert_called_once_with(expected_crop_box)
        
        # Construct expected save path
        base, ext = os.path.splitext(os.path.basename(original_path))
        if not ext: # Handle no extension case from main code
            ext = ".png"
        expected_filename = f"{base}_{fixed_timestamp_str}{ext}"
        expected_save_path = os.path.join(os.path.dirname(original_path), expected_filename)
        
        mock_cropped_image.save.assert_called_once_with(expected_save_path)
        self.mock_messagebox.showinfo.assert_called_once() # Assuming success

    def test_crop_no_zoom_no_pan_image_larger_than_canvas(self):
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 0
        self.viewer.image_y = 0
        self.viewer.image_path = "/dummy/path/image.png"
        expected_crop = (0, 0, 600, 400)
        self.common_crop_save_test_logic(original_path=self.viewer.image_path, expected_crop_box=expected_crop)

    def test_crop_with_zoom_in_no_pan(self):
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 2.0
        self.viewer.image_x = -300 
        self.viewer.image_y = -200
        self.viewer.image_path = "/dummy/path/image.jpg"
        expected_crop = (150, 100, 450, 300)
        self.common_crop_save_test_logic(original_path=self.viewer.image_path, expected_crop_box=expected_crop)

    def test_crop_with_zoom_out_image_smaller_than_canvas(self):
        self.set_canvas_dimensions(1200, 900)
        self.viewer.zoom_factor = 0.5
        self.viewer.image_x = 350
        self.viewer.image_y = 262 
        self.viewer.image_path = "/dummy/path/image.gif"
        expected_crop = (0, 0, 1000, 750) # Assuming original image is 1000x750
        self.common_crop_save_test_logic(original_path=self.viewer.image_path, expected_crop_box=expected_crop)

    def test_crop_panned_right_down_zoomed(self):
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = -200
        self.viewer.image_y = -100
        self.viewer.image_path = "/dummy/path/image.bmp"
        expected_crop = (200, 100, 800, 500)
        self.common_crop_save_test_logic(original_path=self.viewer.image_path, expected_crop_box=expected_crop)

    def test_crop_panned_so_canvas_shows_only_background(self):
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 1000 
        self.viewer.image_y = 750
        self.viewer.image_path = "/dummy/path/image.png" # Path must be set for early exit check
        
        self.viewer.save_cropped_image()
        
        self.mock_messagebox.showerror.assert_called_once()
        self.viewer.image.crop.assert_not_called()

    def test_crop_image_completely_within_canvas_original_size(self):
        self.mock_pil_image.width = 300
        self.mock_pil_image.height = 200
        self.mock_pil_image.size = (300, 200)
        self.viewer.image = self.mock_pil_image

        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 50 
        self.viewer.image_y = 50
        self.viewer.image_path = "/path/small_image.png"
        expected_crop = (0, 0, 300, 200)
        self.common_crop_save_test_logic(original_path=self.viewer.image_path, expected_crop_box=expected_crop)

    def test_crop_top_left_clamping(self):
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 100 
        self.viewer.image_y = 50
        self.viewer.image_path = "/path/image_clamp_tl.png"
        expected_crop = (0, 0, 500, 350)
        self.common_crop_save_test_logic(original_path=self.viewer.image_path, expected_crop_box=expected_crop)

    def test_crop_bottom_right_clamping(self):
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = -800 
        self.viewer.image_y = -600 
        self.viewer.image_path = "/path/image_clamp_br.png"
        expected_crop = (800, 600, 1000, 750) 
        self.common_crop_save_test_logic(original_path=self.viewer.image_path, expected_crop_box=expected_crop)

    # --- New tests for save_cropped_image specific to filename generation and path handling ---
    def test_save_no_image_path(self):
        """Test save attempt when image_path is None."""
        self.viewer.image_path = None
        self.viewer.save_cropped_image()
        self.mock_messagebox.showerror.assert_called_once_with("Error", "Original image path is not known. Cannot save automatically.")
        self.viewer.image.crop.assert_not_called()

    @patch('image_viewer.os.path')
    @patch('image_viewer.datetime')
    def test_save_preserves_original_extension_jpg(self, mock_dt, mock_os_path):
        self.viewer.image_path = "/dummy/path/photo.jpg" # JPG extension
        expected_crop = (0,0,100,100) # Dummy crop box for this test focus
        self.viewer.image_x = 0; self.viewer.image_y = 0; self.viewer.zoom_factor = 1.0;
        self.set_canvas_dimensions(100,100) # Make crop box calculation simple

        self.common_crop_save_test_logic(mock_dt=mock_dt, mock_os_path=mock_os_path,
                                         original_path=self.viewer.image_path,
                                         expected_crop_box=expected_crop,
                                         fixed_timestamp_str="20230101103000")
        # Assertion for filename construction is inside common_crop_save_test_logic

    @patch('image_viewer.os.path')
    @patch('image_viewer.datetime')
    def test_save_defaults_to_png_for_no_extension(self, mock_dt, mock_os_path):
        self.viewer.image_path = "/dummy/path/image_no_ext" # No extension
        expected_crop = (0,0,100,100)
        self.viewer.image_x = 0; self.viewer.image_y = 0; self.viewer.zoom_factor = 1.0;
        self.set_canvas_dimensions(100,100)

        self.common_crop_save_test_logic(mock_dt=mock_dt, mock_os_path=mock_os_path,
                                         original_path=self.viewer.image_path,
                                         expected_crop_box=expected_crop,
                                         fixed_timestamp_str="20230101103000")
        # Expected filename in common_crop_save_test_logic will be image_no_ext_20230101103000.png

    @patch('image_viewer.os.path')
    @patch('image_viewer.datetime')
    def test_save_handles_empty_extension(self, mock_dt, mock_os_path):
        self.viewer.image_path = "/dummy/path/image_empty_ext." # Empty extension
        expected_crop = (0,0,100,100)
        self.viewer.image_x = 0; self.viewer.image_y = 0; self.viewer.zoom_factor = 1.0;
        self.set_canvas_dimensions(100,100)

        self.common_crop_save_test_logic(mock_dt=mock_dt, mock_os_path=mock_os_path,
                                         original_path=self.viewer.image_path,
                                         expected_crop_box=expected_crop,
                                         fixed_timestamp_str="20230101103000")
        # Expected filename in common_crop_save_test_logic will be image_empty_ext._20230101103000.png


if __name__ == '__main__':
    unittest.main()
