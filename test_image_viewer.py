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
        # Mock the Tkinter root window - this is self.viewer.master
        self.mock_master = MagicMock(spec=['after', 'after_cancel', 'title', 'bind', 'config', 'quit', 'update_idletasks', 'geometry'])
        self.mock_master.after.return_value = "timer_id_123" # Mock timer ID
        self.mock_master.winfo_width.return_value = 800 
        self.mock_master.winfo_height.return_value = 600

        # Patch the Canvas and other Tkinter UI elements that ImageViewer creates internally
        with patch('image_viewer.Canvas', MagicMock()) as self.mock_canvas_constructor, \
             patch('image_viewer.Menu', MagicMock()): # Menu is also created in __init__
            self.viewer = ImageViewer(self.mock_master) # Pass the fully mocked master
            self.viewer.canvas = self.mock_canvas_constructor.return_value

        # Set default canvas dimensions for tests
        self.viewer.canvas.winfo_width.return_value = 600
        self.viewer.canvas.winfo_height.return_value = 400
        self.viewer.image_on_canvas = "mock_canvas_item_id" # Simulate image item exists

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
        self.assertIsNotNone(self.viewer.image_on_canvas) # Check if image_on_canvas is set

    # --- Pan Logic Tests ---
    def test_pan_image_updates_coords_and_calls_canvas_coords(self):
        """Test that pan_image updates image_x, image_y and calls canvas.coords."""
        self.viewer.image = self.mock_pil_image # Ensure image is loaded
        self.viewer.image_on_canvas = "test_image_id" # Ensure image_on_canvas is set

        # Initial position
        self.viewer.image_x = 10
        self.viewer.image_y = 20
        self.viewer.drag_start_x = 50
        self.viewer.drag_start_y = 50
        self.viewer.dragging = True

        mock_event = self.create_mock_event(x=60, y=75) # Pan by dx=10, dy=25

        with patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer.pan_image(mock_event)

            # Check new coordinates
            self.assertEqual(self.viewer.image_x, 10 + 10) # 20
            self.assertEqual(self.viewer.image_y, 20 + 25) # 45
            # Check drag_start is updated
            self.assertEqual(self.viewer.drag_start_x, 60)
            self.assertEqual(self.viewer.drag_start_y, 75)

            # Check canvas.coords was called
            self.viewer.canvas.coords.assert_called_once_with("test_image_id", 20, 45)
            # Check update_display was NOT called
            mock_update_display.assert_not_called()

    def test_pan_image_does_nothing_if_not_dragging(self):
        self.viewer.dragging = False # Ensure not dragging
        initial_x = self.viewer.image_x
        initial_y = self.viewer.image_y
        mock_event = self.create_mock_event(x=60, y=75)

        with patch.object(self.viewer.canvas, 'coords') as mock_canvas_coords, \
             patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer.pan_image(mock_event)
            self.assertEqual(self.viewer.image_x, initial_x)
            self.assertEqual(self.viewer.image_y, initial_y)
            mock_canvas_coords.assert_not_called()
            mock_update_display.assert_not_called()

    def test_pan_image_fallback_to_update_display_if_no_canvas_item(self):
        self.viewer.image_on_canvas = None # Simulate no canvas item ID
        self.viewer.dragging = True
        self.viewer.drag_start_x = 0
        self.viewer.drag_start_y = 0
        mock_event = self.create_mock_event(x=10, y=10)

        with patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer.pan_image(mock_event)
            mock_update_display.assert_called_once() # Fallback was called


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
        """Test basic zoom-in functionality (parameter calculation)."""
        initial_zoom = self.viewer.zoom_factor
        mock_event = self.create_mock_event(x=100, y=100, delta=120)
        
        with patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer.zoom_image(mock_event)
            self.assertGreater(self.viewer.zoom_factor, initial_zoom)
            mock_update_display.assert_not_called() # Should not be called directly
            self.viewer.master.after.assert_called_once() # Check if scheduled

    def test_zoom_out(self):
        """Test basic zoom-out functionality (parameter calculation)."""
        initial_zoom = self.viewer.zoom_factor
        mock_event = self.create_mock_event(x=100, y=100, delta=-120)
        
        with patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer.zoom_image(mock_event)
            self.assertLess(self.viewer.zoom_factor, initial_zoom)
            mock_update_display.assert_not_called()
            self.viewer.master.after.assert_called_once()

    def test_zoom_limits(self):
        """Test that zoom factor is clamped (parameter calculation)."""
        with patch.object(self.viewer, 'update_display'), \
             patch.object(self.viewer.master, 'after') as mock_master_after: # Ensure after is checkable
            # Zoom in excessively
            for _ in range(50):
                self.viewer.zoom_image(self.create_mock_event(100, 100, delta=120))
            self.assertAlmostEqual(self.viewer.zoom_factor, 5.0, places=5)
            # Check that master.after was called for each zoom_image call
            self.assertEqual(mock_master_after.call_count, 50) 


            # Reset zoom and image position for the next part of test
            self.viewer.zoom_factor = 1.0 
            self.viewer.image_x = 0 
            self.viewer.image_y = 0
            # Reset mock_master_after call count for the next batch of calls
            mock_master_after.reset_mock()

            # Zoom out excessively
            for _ in range(50):
                self.viewer.zoom_image(self.create_mock_event(100, 100, delta=-120))
            self.assertAlmostEqual(self.viewer.zoom_factor, 0.1, places=5)
            self.assertEqual(mock_master_after.call_count, 50)
        
    def test_zoom_towards_cursor_calculation(self):
        """Test the core logic of zooming towards the cursor (parameter calculation)."""
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 0 
        self.viewer.image_y = 0
        
        mouse_x_on_canvas = 100
        mouse_y_on_canvas = 75
        mock_event = self.create_mock_event(mouse_x_on_canvas, mouse_y_on_canvas, delta=120)
        
        with patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer.zoom_image(mock_event)

            new_zoom_factor = self.viewer.zoom_factor 
            expected_image_x = mouse_x_on_canvas - (100 * new_zoom_factor)
            expected_image_y = mouse_y_on_canvas - (75 * new_zoom_factor)
            
            self.assertAlmostEqual(self.viewer.image_x, expected_image_x, places=5)
            self.assertAlmostEqual(self.viewer.image_y, expected_image_y, places=5)
            self.assertAlmostEqual((mouse_x_on_canvas - self.viewer.image_x) / self.viewer.zoom_factor, 100, places=3)
            self.assertAlmostEqual((mouse_y_on_canvas - self.viewer.image_y) / self.viewer.zoom_factor, 75, places=3)
            
            mock_update_display.assert_not_called()
            self.viewer.master.after.assert_called_once()

    def test_zoom_image_schedules_update_and_calculates_params(self):
        self.viewer.image = self.mock_pil_image 
        self.viewer.image_path = "/fake/path.png" 
        initial_zoom = self.viewer.zoom_factor = 1.0 # Set specific initial state
        initial_x = self.viewer.image_x = 0
        initial_y = self.viewer.image_y = 0

        mock_event = self.create_mock_event(x=100, y=100, delta=120) 
        
        # self.viewer.master is already mocked in setUp
        self.viewer.master.after.return_value = "timer1" # Ensure specific timer ID
        
        with patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer.zoom_image(mock_event)

            self.assertNotEqual(self.viewer.zoom_factor, initial_zoom)
            self.assertNotEqual(self.viewer.image_x, initial_x)
            self.assertNotEqual(self.viewer.image_y, initial_y)
            mock_update_display.assert_not_called()
            self.viewer.master.after.assert_called_once_with(100, self.viewer._perform_zoom_update)
            self.assertEqual(self.viewer.zoom_debounce_timer, "timer1")

    def test_zoom_image_cancels_pending_timer(self):
        self.viewer.image = self.mock_pil_image
        self.viewer.zoom_debounce_timer = "old_timer_id" # Simulate a pending timer
        
        mock_event = self.create_mock_event(x=100, y=100, delta=120)
        
        self.viewer.master.after.return_value = "new_timer_id"

        self.viewer.zoom_image(mock_event)
        
        self.viewer.master.after_cancel.assert_called_once_with("old_timer_id")
        self.viewer.master.after.assert_called_once_with(100, self.viewer._perform_zoom_update)
        self.assertEqual(self.viewer.zoom_debounce_timer, "new_timer_id")

    def test_perform_zoom_update_calls_update_display(self):
        self.viewer.image = self.mock_pil_image 
        self.viewer.zoom_debounce_timer = "some_timer_id" 
        
        with patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer._perform_zoom_update()
            mock_update_display.assert_called_once()
            self.assertIsNone(self.viewer.zoom_debounce_timer)


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

    # --- Keyboard Navigation & Path Normalization Tests ---

    @patch('image_viewer.Image.open')
    @patch('image_viewer.os') # Mock the entire os module used by image_viewer
    def test_open_image_populates_image_list_and_index_with_normalization(self, mock_os_module, mock_image_open):
        """Test directory scanning with path normalization."""
        mock_image_open.return_value = self.mock_pil_image

        # Setup mock os module functions
        fake_dir_unnormalized = '/fake/./directory' # Path with components needing normalization
        fake_dir_normalized = os.path.normcase(os.path.abspath(fake_dir_unnormalized))

        # File to open (varied case)
        current_file_unnormalized = 'img2.JPG' 
        current_filepath_unnormalized = os.path.join(fake_dir_unnormalized, current_file_unnormalized)
        
        # Expected normalized path for the opened image
        expected_opened_path_normalized = os.path.normcase(os.path.abspath(current_filepath_unnormalized))

        # Mock os.path functions
        mock_os_module.path.dirname.return_value = fake_dir_unnormalized # dirname is called on the input path
        mock_os_module.path.abspath.side_effect = os.path.abspath # Use real abspath
        mock_os_module.path.normcase.side_effect = os.path.normcase # Use real normcase
        mock_os_module.path.join.side_effect = os.path.join # Use real join
        
        # Mock os.listdir to return names that also might need normalization/casing adjustments
        mock_os_module.listdir.return_value = ['img1.png', 'IMG2.jpg', 'text.txt', 'img3.bmp', 'IMG0.gif', 'subdir']
        
        def isfile_side_effect(path):
            # This path will be already joined by os.path.join
            # We need to compare with the names os.listdir returns
            return os.path.basename(path) != 'subdir'
        mock_os_module.path.isfile.side_effect = isfile_side_effect

        # Call open_image with the unnormalized path
        self.viewer.open_image(filepath=current_filepath_unnormalized)

        # Assert that self.viewer.image_path is normalized
        self.assertEqual(self.viewer.image_path, expected_opened_path_normalized)

        # Construct expected_image_list with normalized paths
        expected_image_list_normalized = sorted([
            os.path.normcase(os.path.abspath(os.path.join(fake_dir_unnormalized, 'IMG0.gif'))),
            os.path.normcase(os.path.abspath(os.path.join(fake_dir_unnormalized, 'img1.png'))),
            os.path.normcase(os.path.abspath(os.path.join(fake_dir_unnormalized, 'IMG2.jpg'))), # Note: IMG2.jpg from listdir
            os.path.normcase(os.path.abspath(os.path.join(fake_dir_unnormalized, 'img3.bmp'))),
        ])
        
        self.assertEqual(self.viewer.image_list, expected_image_list_normalized)
        
        # Find the index of the *opened* image (expected_opened_path_normalized)
        # which should match IMG2.jpg from listdir after normalization
        # If current_filepath_unnormalized was 'img2.JPG', its normalized form should match one in the list.
        # The file 'IMG2.jpg' from listdir, when normalized, should match 'img2.JPG' normalized.
        
        # Need to find the expected index carefully based on the opened path.
        # The opened path is current_filepath_unnormalized ('img2.JPG').
        # Its normalized form is expected_opened_path_normalized.
        # The list contains normalized 'IMG2.jpg'. These should match if normcase works.
        try:
            expected_index = expected_image_list_normalized.index(expected_opened_path_normalized)
        except ValueError:
            self.fail(f"Normalized opened path {expected_opened_path_normalized} not found in normalized list {expected_image_list_normalized}")

        self.assertEqual(self.viewer.current_image_index, expected_index)


    @patch('image_viewer.Image.open')
    @patch('image_viewer.os')
    def test_open_image_handles_empty_directory(self, mock_os, mock_image_open):
        mock_image_open.return_value = self.mock_pil_image
        fake_dir = '/fake/empty_dir'
        current_filepath = os.path.join(fake_dir, 'img1.png')
        mock_os.path.dirname.return_value = fake_dir
        mock_os.listdir.return_value = []
        mock_os.path.isfile.return_value = True 
        mock_os.path.join.side_effect = os.path.join

        self.viewer.open_image(filepath=current_filepath)
        self.assertEqual(self.viewer.image_list, [])
        self.assertEqual(self.viewer.current_image_index, -1)

    @patch('image_viewer.Image.open')
    @patch('image_viewer.os')
    def test_open_image_handles_directory_with_no_images(self, mock_os, mock_image_open):
        mock_image_open.return_value = self.mock_pil_image
        fake_dir = '/fake/no_images_dir'
        current_filepath = os.path.join(fake_dir, 'anything.txt') # Not an image, but open_image will still scan
        self.viewer.image_path = current_filepath # Simulate it was set
        
        mock_os.path.dirname.return_value = fake_dir
        mock_os.listdir.return_value = ['file.txt', 'document.doc']
        mock_os.path.isfile.return_value = True
        mock_os.path.join.side_effect = os.path.join

        # Need to ensure Image.open doesn't fail for 'anything.txt' if we pass it to open_image
        # The current open_image logic always tries to Image.open(filepath) first.
        # For this specific test, we are testing the list population part.
        # We can assume 'anything.txt' was somehow "opened" (mocked) and now we test list population.
        # So, directly manipulate image_list and current_image_index setting parts
        # or ensure filepath passed to open_image is a mock-openable image.

        # Let's make the 'current_filepath' a valid image for the mock_image_open
        mock_image_open.return_value = self.mock_pil_image 
        current_image_for_open = os.path.join(fake_dir, 'dummy_opened.png')
        self.viewer.image_path = current_image_for_open # Set this for the listdir part

        self.viewer.open_image(filepath=current_image_for_open)
        
        self.assertEqual(self.viewer.image_list, [])
        self.assertEqual(self.viewer.current_image_index, -1)

    @patch('image_viewer.Image.open')
    @patch('image_viewer.os')
    def test_open_image_handles_os_error_during_listdir(self, mock_os, mock_image_open):
        mock_image_open.return_value = self.mock_pil_image
        fake_dir = '/fake/error_dir'
        current_filepath = os.path.join(fake_dir, 'img1.png')
        mock_os.path.dirname.return_value = fake_dir
        mock_os.listdir.side_effect = OSError("Permission denied")
        mock_os.path.join.side_effect = os.path.join

        self.viewer.open_image(filepath=current_filepath)
        self.assertEqual(self.viewer.image_list, [])
        self.assertEqual(self.viewer.current_image_index, -1)

    def test_handle_arrow_key_event_calls_load_adjacent(self):
        self.viewer.image_list = ["/img1.png", "/img2.png"] # Ensure image_list is not empty
        with patch.object(self.viewer, '_load_adjacent_image') as mock_load_adj:
            # Test Left key
            mock_event_left = Mock(keysym='Left')
            self.viewer.handle_arrow_key_event(mock_event_left)
            mock_load_adj.assert_called_once_with(-1)
            
            mock_load_adj.reset_mock() # Reset for next call
            
            # Test Right key
            mock_event_right = Mock(keysym='Right')
            self.viewer.handle_arrow_key_event(mock_event_right)
            mock_load_adj.assert_called_once_with(1)

    def test_handle_arrow_key_event_no_list(self):
        self.viewer.image_list = [] # Empty list
        with patch.object(self.viewer, '_load_adjacent_image') as mock_load_adj:
            mock_event_left = Mock(keysym='Left')
            self.viewer.handle_arrow_key_event(mock_event_left)
            mock_load_adj.assert_not_called()

    @patch.object(ImageViewer, 'open_image')
    def test_load_adjacent_image_next(self, mock_open_image_method):
        self.viewer.image_list = ['/path/img1.png', '/path/img2.png', '/path/img3.png']
        self.viewer.current_image_index = 0
        self.viewer._load_adjacent_image(1)
        mock_open_image_method.assert_called_once_with(filepath='/path/img2.png')

    @patch.object(ImageViewer, 'open_image')
    def test_load_adjacent_image_previous(self, mock_open_image_method):
        self.viewer.image_list = ['/path/img1.png', '/path/img2.png', '/path/img3.png']
        self.viewer.current_image_index = 1
        self.viewer._load_adjacent_image(-1)
        mock_open_image_method.assert_called_once_with(filepath='/path/img1.png')

    @patch.object(ImageViewer, 'open_image')
    def test_load_adjacent_image_next_at_end(self, mock_open_image_method):
        self.viewer.image_list = ['/path/img1.png', '/path/img2.png', '/path/img3.png']
        self.viewer.current_image_index = 2 # Last image
        self.viewer._load_adjacent_image(1)
        mock_open_image_method.assert_not_called()

    @patch.object(ImageViewer, 'open_image')
    def test_load_adjacent_image_previous_at_start(self, mock_open_image_method):
        self.viewer.image_list = ['/path/img1.png', '/path/img2.png', '/path/img3.png']
        self.viewer.current_image_index = 0 # First image
        self.viewer._load_adjacent_image(-1)
        mock_open_image_method.assert_not_called()

    @patch.object(ImageViewer, 'open_image')
    def test_load_adjacent_image_empty_list(self, mock_open_image_method):
        self.viewer.image_list = []
        self.viewer.current_image_index = -1
        self.viewer._load_adjacent_image(1)
        mock_open_image_method.assert_not_called()
        self.viewer._load_adjacent_image(-1)
        mock_open_image_method.assert_not_called()
        
    @patch.object(ImageViewer, 'open_image')
    def test_load_adjacent_image_invalid_index(self, mock_open_image_method):
        self.viewer.image_list = ['/path/img1.png', '/path/img2.png']
        self.viewer.current_image_index = -1 # Invalid index
        self.viewer._load_adjacent_image(1)
        mock_open_image_method.assert_not_called()

    # --- Fit-to-Window on Resize Tests ---
    def test_fit_image_to_canvas_logic(self):
        """Test the _fit_image_to_canvas method directly."""
        self.viewer.image = self.mock_pil_image # 1000x750
        
        # Case 1: Image larger than canvas, landscape canvas
        self.viewer._fit_image_to_canvas(target_canvas_width=500, target_canvas_height=300)
        # Width ratio: 500/1000 = 0.5. Height ratio: 300/750 = 0.4. Min ratio = 0.4
        self.assertAlmostEqual(self.viewer.zoom_factor, 0.4)
        expected_w, expected_h = 1000 * 0.4, 750 * 0.4 # 400, 300
        self.assertAlmostEqual(self.viewer.image_x, (500 - expected_w) / 2) # (500-400)/2 = 50
        self.assertAlmostEqual(self.viewer.image_y, (300 - expected_h) / 2) # (300-300)/2 = 0

        # Case 2: Image smaller than canvas
        self.viewer._fit_image_to_canvas(target_canvas_width=2000, target_canvas_height=1500)
        # Width ratio: 2000/1000 = 2. Height ratio: 1500/750 = 2. Min ratio = 2
        self.assertAlmostEqual(self.viewer.zoom_factor, 2.0)
        expected_w, expected_h = 1000 * 2.0, 750 * 2.0 # 2000, 1500
        self.assertAlmostEqual(self.viewer.image_x, (2000 - expected_w) / 2) # 0
        self.assertAlmostEqual(self.viewer.image_y, (1500 - expected_h) / 2) # 0

        # Case 3: Canvas forces letterboxing (image aspect wider than canvas aspect)
        self.viewer.image.size = (1000, 500) # Image 2:1
        self.viewer._fit_image_to_canvas(target_canvas_width=500, target_canvas_height=500) # Canvas 1:1
        # Width ratio: 500/1000 = 0.5. Height ratio: 500/500 = 1.0. Min ratio = 0.5
        self.assertAlmostEqual(self.viewer.zoom_factor, 0.5)
        expected_w, expected_h = 1000 * 0.5, 500 * 0.5 # 500, 250
        self.assertAlmostEqual(self.viewer.image_x, (500 - expected_w) / 2) # 0
        self.assertAlmostEqual(self.viewer.image_y, (500 - expected_h) / 2) # (500-250)/2 = 125

        # Case 4: Zero dimension canvas (should default to zoom 1.0)
        self.viewer.image.size = (1000,750) # Reset
        self.viewer._fit_image_to_canvas(target_canvas_width=0, target_canvas_height=500)
        self.assertAlmostEqual(self.viewer.zoom_factor, 1.0)

    def test_handle_window_resize_debounces_update(self):
        """Test that handle_window_resize correctly debounces calls."""
        self.viewer.resize_debounce_timer = "old_timer_id" # Simulate existing timer
        mock_event = Mock(widget=self.viewer.master) # Simulate event on master

        self.viewer.master.after.return_value = "new_timer_id" # For the new timer

        self.viewer.handle_window_resize(mock_event)

        self.viewer.master.after_cancel.assert_called_once_with("old_timer_id")
        self.viewer.master.after.assert_called_once_with(200, self.viewer._perform_fit_to_window_update)
        self.assertEqual(self.viewer.resize_debounce_timer, "new_timer_id")
    
    def test_handle_window_resize_ignores_other_widget_events(self):
        mock_event = Mock(widget=self.viewer.canvas) # Event from a different widget
        self.viewer.handle_window_resize(mock_event)
        self.viewer.master.after_cancel.assert_not_called()
        self.viewer.master.after.assert_not_called()


    def test_perform_fit_to_window_update_calls_fit_and_display(self):
        """Test _perform_fit_to_window_update logic."""
        self.viewer.image = self.mock_pil_image # Ensure image is loaded
        self.viewer.resize_debounce_timer = "some_timer_id"

        with patch.object(self.viewer, '_fit_image_to_canvas', return_value=True) as mock_fit, \
             patch.object(self.viewer, 'update_display') as mock_update_display:
            
            self.viewer._perform_fit_to_window_update()

            mock_fit.assert_called_once()
            mock_update_display.assert_called_once()
            self.assertIsNone(self.viewer.resize_debounce_timer)

    def test_perform_fit_to_window_update_no_image(self):
        self.viewer.image = None
        with patch.object(self.viewer, '_fit_image_to_canvas') as mock_fit, \
             patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer._perform_fit_to_window_update()
            mock_fit.assert_not_called() # Should not be called if no image
            mock_update_display.assert_not_called()

    # --- Ctrl+O Shortcut Test ---
    @patch('image_viewer.filedialog.askopenfilename') # Patch where it's used
    def test_ctrl_o_shortcut_triggers_open_image_dialog(self, mock_askopenfilename):
        """Test that Ctrl+O shortcut triggers the open image dialog via open_image()."""
        # The binding is master.bind('<Control-o>', lambda event: self.open_image())
        # We need to get this lambda or simulate its effect.
        # Directly calling open_image() with no args is equivalent to what the lambda does.
        
        # Simulate the call that the lambda would make
        self.viewer.open_image() 
        
        mock_askopenfilename.assert_called_once()


if __name__ == '__main__':
    unittest.main()
