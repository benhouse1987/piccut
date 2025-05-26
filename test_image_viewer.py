import unittest
from unittest.mock import Mock, patch, MagicMock
import os # For os.path.join, os.path.splitext if used directly
from datetime import datetime
from PIL import Image # Added import

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
                                    fixed_timestamp_str="20230101103000",
                                    crop_target_image=None): 
        """
        Refactored helper for testing save_cropped_image.
        Mocks datetime and os.path, calls save_cropped_image, 
        and asserts the crop box and save path.
        """
        mock_dt.now.return_value = datetime(2023, 1, 1, 10, 30, 0)
        self.viewer.image_path = original_path
        
        mock_os_path.dirname.return_value = os.path.dirname(original_path)
        mock_os_path.basename.return_value = os.path.basename(original_path)
        mock_os_path.splitext.side_effect = os.path.splitext
        mock_os_path.join.side_effect = os.path.join

        mock_cropped_image_result = MagicMock()
        
        # Determine which image's crop method to check.
        # This is crucial for proxy tests where self.original_image.crop is called.
        target_for_crop_method = crop_target_image if crop_target_image is not None else self.viewer.image
        
        # Ensure the target_for_crop_method (e.g. self.viewer.original_image) has a mock 'crop'
        if not isinstance(target_for_crop_method.crop, MagicMock):
            target_for_crop_method.crop = MagicMock() # If it's not a mock, make it one for assertion
        target_for_crop_method.crop.return_value = mock_cropped_image_result
        
        self.viewer.save_cropped_image()

        target_for_crop_method.crop.assert_called_once_with(expected_crop_box)
        
        base, ext = os.path.splitext(os.path.basename(original_path))
        if not ext:
            ext = ".png"
        expected_filename = f"{base}_{fixed_timestamp_str}{ext}"
        expected_save_path = os.path.join(os.path.dirname(original_path), expected_filename)
        
        mock_cropped_image_result.save.assert_called_once_with(expected_save_path) 
        self.mock_messagebox.showinfo.assert_called_once()

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

    # --- Proxy Image Tests ---
    @patch('image_viewer.Image.open')
    @patch('image_viewer.os') # For path operations within open_image
    def test_open_image_creates_proxy_for_large_image(self, mock_os_module, mock_image_open_func):
        # Use constants from the module if accessible, otherwise redefine or use values
        # For simplicity, using values directly here, matching those in image_viewer.py
        PROXY_CREATION_THRESHOLD_DIM = 6000 # This remains unchanged
        PROXY_MAX_TARGET_DIM_FOR_TEST = 3000 # Updated for this test to match new app logic

        # Example large image dimensions (ensure one dimension is > PROXY_CREATION_THRESHOLD_DIM)
        # Let's use dimensions where width is greater to specifically test that path.
        large_width, large_height = PROXY_CREATION_THRESHOLD_DIM + 1000, PROXY_CREATION_THRESHOLD_DIM - 1000 
        # e.g., 7000x5000. Original PROXY_MAX_TARGET_DIM was 6000, now 3000 for test.
        
        mock_loaded_image = MagicMock(spec=Image.Image)
        mock_loaded_image.size = (large_width, large_height)
        mock_loaded_image.width = large_width
        mock_loaded_image.height = large_height
        
        mock_resized_proxy = MagicMock(spec=Image.Image) # This is what resize should return
        
        # Calculate expected proxy dimensions based on PROXY_MAX_TARGET_DIM_FOR_TEST (3000)
        # This logic mirrors the one in image_viewer.py
        if large_width > large_height:
            scale_factor = PROXY_MAX_TARGET_DIM_FOR_TEST / large_width
            expected_proxy_w = PROXY_MAX_TARGET_DIM_FOR_TEST
            expected_proxy_h = int(large_height * scale_factor)
        else:
            scale_factor = PROXY_MAX_TARGET_DIM_FOR_TEST / large_height
            expected_proxy_h = PROXY_MAX_TARGET_DIM_FOR_TEST
            expected_proxy_w = int(large_width * scale_factor)
        
        # Ensure dimensions are at least 1 (matching image_viewer.py logic)
        expected_proxy_w = max(1, expected_proxy_w)
        expected_proxy_h = max(1, expected_proxy_h)

        mock_resized_proxy.size = (expected_proxy_w, expected_proxy_h)
        mock_resized_proxy.width = expected_proxy_w
        mock_resized_proxy.height = expected_proxy_h

        mock_loaded_image.resize.return_value = mock_resized_proxy
        mock_image_open_func.return_value = mock_loaded_image

        # Mock os.path functions needed by open_image's directory scanning part
        mock_os_module.path.dirname.return_value = "/fake/dir"
        mock_os_module.listdir.return_value = [] # No other images for simplicity of this test
        mock_os_module.path.abspath.side_effect = lambda x: x # Passthrough
        mock_os_module.path.normcase.side_effect = lambda x: x # Passthrough
        mock_os_module.path.join.side_effect = os.path.join

        self.viewer.open_image(filepath="/fake/dir/large_image.png")

        self.assertIs(self.viewer.original_image, mock_loaded_image)
        self.assertEqual(self.viewer.original_width, large_width)
        self.assertEqual(self.viewer.original_height, large_height)
        self.assertIsNot(self.viewer.image, self.viewer.original_image, "Proxy should be different from original")
        self.assertIs(self.viewer.image, mock_resized_proxy, "Proxy should be the resized image")
        
        mock_loaded_image.resize.assert_called_once_with(
            (expected_proxy_w, expected_proxy_h), Image.Resampling.BICUBIC
        )

    @patch('image_viewer.Image.open')
    @patch('image_viewer.os')
    def test_open_image_uses_original_for_small_image(self, mock_os_module, mock_image_open_func):
        small_width, small_height = 1000, 800
        mock_loaded_image = MagicMock(spec=Image.Image)
        mock_loaded_image.size = (small_width, small_height)
        mock_loaded_image.width = small_width
        mock_loaded_image.height = small_height
        mock_image_open_func.return_value = mock_loaded_image

        mock_os_module.path.dirname.return_value = "/fake/dir"
        mock_os_module.listdir.return_value = []
        mock_os_module.path.abspath.side_effect = lambda x: x
        mock_os_module.path.normcase.side_effect = lambda x: x
        mock_os_module.path.join.side_effect = os.path.join


        self.viewer.open_image(filepath="/fake/dir/small_image.png")

        self.assertIs(self.viewer.original_image, mock_loaded_image)
        self.assertEqual(self.viewer.original_width, small_width)
        self.assertEqual(self.viewer.original_height, small_height)
        self.assertIs(self.viewer.image, self.viewer.original_image) # Original is used
        mock_loaded_image.resize.assert_not_called() # Resize for proxy creation not called

    @patch('image_viewer.Image.open')
    @patch('image_viewer.os')
    def test_open_image_handles_proxy_creation_failure(self, mock_os_module, mock_image_open_func):
        PROXY_CREATION_THRESHOLD_DIM = 6000
        large_width, large_height = PROXY_CREATION_THRESHOLD_DIM + 100, PROXY_CREATION_THRESHOLD_DIM + 100

        mock_loaded_image = MagicMock(spec=Image.Image)
        mock_loaded_image.size = (large_width, large_height)
        mock_loaded_image.width = large_width
        mock_loaded_image.height = large_height
        mock_loaded_image.resize.side_effect = Exception("Resize error") # Simulate failure
        mock_image_open_func.return_value = mock_loaded_image
        
        mock_os_module.path.dirname.return_value = "/fake/dir"
        mock_os_module.listdir.return_value = []
        mock_os_module.path.abspath.side_effect = lambda x: x
        mock_os_module.path.normcase.side_effect = lambda x: x
        mock_os_module.path.join.side_effect = os.path.join

        self.viewer.open_image(filepath="/fake/dir/large_image_fail_proxy.png")

        self.assertIs(self.viewer.original_image, mock_loaded_image)
        self.assertIs(self.viewer.image, self.viewer.original_image) # Fallback to original
        mock_loaded_image.resize.assert_called_once() # Attempt was made

    @patch('image_viewer.os.path')
    @patch('image_viewer.datetime')
    def test_save_cropped_image_with_proxy_translates_coords(self, mock_dt, mock_os_path):
        # Original image is large, proxy is smaller
        self.viewer.original_width, self.viewer.original_height = 8000, 6000
        self.viewer.original_image = MagicMock(spec=Image.Image)
        self.viewer.original_image.size = (self.viewer.original_width, self.viewer.original_height)
        
        # Proxy (self.image is the proxy)
        proxy_width, proxy_height = 4000, 3000 
        self.viewer.image = MagicMock(spec=Image.Image)
        self.viewer.image.size = (proxy_width, proxy_height)
        self.viewer.image.width = proxy_width
        self.viewer.image.height = proxy_height
        
        self.viewer.image_path = "/fake/dir/proxy_test.png" # Needed for save location

        # View parameters (relative to the proxy image when zoomed)
        self.viewer.zoom_factor = 2.0 # Zoomed into the proxy
        self.viewer.image_x = -1000 # Proxy panned left by 1000px
        self.viewer.image_y = -500  # Proxy panned up by 500px
        self.set_canvas_dimensions(600, 400) # Canvas size

        # Calculations based on save_cropped_image logic:
        # 1. Visible part of zoomed proxy, in proxy's own scaled coords:
        vis_x1_on_proxy_scaled = -self.viewer.image_x # 1000
        vis_y1_on_proxy_scaled = -self.viewer.image_y # 500
        vis_x2_on_proxy_scaled = vis_x1_on_proxy_scaled + 600 # 1600
        vis_y2_on_proxy_scaled = vis_y1_on_proxy_scaled + 400 # 900
        
        # 2. Convert to unzoomed proxy coords:
        crop_x1_on_proxy = vis_x1_on_proxy_scaled / self.viewer.zoom_factor # 1000/2 = 500
        crop_y1_on_proxy = vis_y1_on_proxy_scaled / self.viewer.zoom_factor # 500/2 = 250
        crop_x2_on_proxy = vis_x2_on_proxy_scaled / self.viewer.zoom_factor # 1600/2 = 800
        crop_y2_on_proxy = vis_y2_on_proxy_scaled / self.viewer.zoom_factor # 900/2 = 450

        # 3. Translate to original image coords:
        scale_to_original_x = self.viewer.original_width / proxy_width   # 8000/4000 = 2
        scale_to_original_y = self.viewer.original_height / proxy_height # 6000/3000 = 2
        
        final_crop_x1_on_original = crop_x1_on_proxy * scale_to_original_x # 500*2 = 1000
        final_crop_y1_on_original = crop_y1_on_proxy * scale_to_original_y # 250*2 = 500
        final_crop_x2_on_original = crop_x2_on_proxy * scale_to_original_x # 800*2 = 1600
        final_crop_y2_on_original = crop_y2_on_proxy * scale_to_original_y # 450*2 = 900
        
        # 4. Clamping (these coords are within original 8000x6000)
        expected_crop_box_on_original = (
            int(round(final_crop_x1_on_original)), # 1000
            int(round(final_crop_y1_on_original)), # 500
            int(round(final_crop_x2_on_original)), # 1600
            int(round(final_crop_y2_on_original))  # 900
        )
        
        self.common_crop_save_test_logic(mock_dt, mock_os_path, 
                                         original_path=self.viewer.image_path, 
                                         expected_crop_box=expected_crop_box_on_original,
                                         crop_target_image=self.viewer.original_image) # Crucial: assert on original_image

    @patch('image_viewer.os.path')
    @patch('image_viewer.datetime')
    def test_save_cropped_image_no_proxy_uses_direct_coords(self, mock_dt, mock_os_path):
        # Original image is small enough, no proxy
        self.viewer.original_width, self.viewer.original_height = 1000, 750
        self.viewer.original_image = MagicMock(spec=Image.Image)
        self.viewer.original_image.size = (self.viewer.original_width, self.viewer.original_height)
        self.viewer.image = self.viewer.original_image # No proxy
        
        self.viewer.image_path = "/fake/dir/no_proxy_test.png"

        self.viewer.zoom_factor = 1.0 # No zoom
        self.viewer.image_x = -50  # Panned left by 50
        self.viewer.image_y = -20  # Panned up by 20
        self.set_canvas_dimensions(300, 200) # Canvas size

        # Calculations:
        vis_x1_on_img_scaled = -self.viewer.image_x # 50
        vis_y1_on_img_scaled = -self.viewer.image_y # 20
        vis_x2_on_img_scaled = vis_x1_on_img_scaled + 300 # 350
        vis_y2_on_img_scaled = vis_y1_on_img_scaled + 200 # 220
        
        crop_x1 = vis_x1_on_img_scaled / self.viewer.zoom_factor # 50
        crop_y1 = vis_y1_on_img_scaled / self.viewer.zoom_factor # 20
        crop_x2 = vis_x2_on_img_scaled / self.viewer.zoom_factor # 350
        crop_y2 = vis_y2_on_img_scaled / self.viewer.zoom_factor # 220
        
        # Clamping to original 1000x750
        expected_crop_box = (
            int(round(max(0, crop_x1))), # 50
            int(round(max(0, crop_y1))), # 20
            int(round(min(self.viewer.original_width, crop_x2))),  # 350
            int(round(min(self.viewer.original_height, crop_y2))) # 220
        )
        
        self.common_crop_save_test_logic(mock_dt, mock_os_path, 
                                         original_path=self.viewer.image_path, 
                                         expected_crop_box=expected_crop_box,
                                         crop_target_image=self.viewer.original_image)


    # --- Keyboard Navigation & Path Normalization Tests ---

    @patch('image_viewer.Image.open')
    @patch('image_viewer.os') # Mock the entire os module used by image_viewer
    def test_open_image_populates_image_list_and_index_and_resets_zoom_state(self, mock_os_module, mock_image_open):
        """Test directory scanning, path normalization, and double-click zoom state reset."""
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
        # Test reset of is_zoomed_to_original_size
        self.assertFalse(self.viewer.is_zoomed_to_original_size)


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
            
            self.viewer.is_zoomed_to_original_size = True # Set before call
            self.viewer._perform_fit_to_window_update()

            mock_fit.assert_called_once()
            mock_update_display.assert_called_once()
            self.assertIsNone(self.viewer.resize_debounce_timer)
            self.assertFalse(self.viewer.is_zoomed_to_original_size) # Verify reset

    def test_perform_fit_to_window_update_no_image(self):
        self.viewer.image = None
        self.viewer.is_zoomed_to_original_size = True # Check it doesn't change if no image
        with patch.object(self.viewer, '_fit_image_to_canvas') as mock_fit, \
             patch.object(self.viewer, 'update_display') as mock_update_display:
            self.viewer._perform_fit_to_window_update()
            mock_fit.assert_not_called() # Should not be called if no image
            mock_update_display.assert_not_called()
            self.assertTrue(self.viewer.is_zoomed_to_original_size) # State unchanged

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

    # --- Escape Key Tests ---
    def test_escape_key_binding(self):
        """Test that the Escape key is bound to the handle_escape_key method."""
        # Check if master.bind was called with '<Escape>' and the correct handler
        escape_binding_found = False
        for call in self.viewer.master.bind.call_args_list:
            args, _ = call
            if args[0] == '<Escape>' and args[1] == self.viewer.handle_escape_key:
                escape_binding_found = True
                break
        self.assertTrue(escape_binding_found, "Escape key not bound to handle_escape_key")

    def test_handle_escape_key_calls_destroy(self):
        """Test that handle_escape_key calls master.destroy."""
        # self.viewer.master is a MagicMock, so self.viewer.master.destroy is also a mock
        self.viewer.handle_escape_key() # Call the handler directly
        self.viewer.master.destroy.assert_called_once()

    def test_update_display_uses_bicubic_resampling_no_rotation(self):
        # Setup: Ensure an image is assigned and it has a size.
        # self.viewer.image is already a MagicMock(spec=Image.Image) from setUp.
        # We need to ensure it's configured for this test.
        current_image_mock = MagicMock(spec=Image.Image)
        current_image_mock.width = 100
        current_image_mock.height = 100
        current_image_mock.size = (100, 100)
        
        # Assign this specifically configured mock to self.viewer.image for this test
        self.viewer.image = current_image_mock
        
        # Set rotation angle to 0 to simplify the path through update_display,
        # ensuring self.viewer.image is the one that .resize is called on (it becomes image_to_be_zoomed).
        self.viewer.current_rotation_angle = 0.0
        
        # Get the .resize mock from our specific image instance for this test
        mock_resize_method_on_instance = self.viewer.image.resize 
        
        # Mock the return value of the resize operation.
        # This is what PhotoImage will be called with.
        mock_resized_result_image = MagicMock(spec=Image.Image) 
        mock_resize_method_on_instance.return_value = mock_resized_result_image

        # Call the method under test
        self.viewer.update_display()

        # Assert that resize was called
        mock_resize_method_on_instance.assert_called()
        
        # Get the arguments from the call to resize
        # call_args gives a tuple (positional_args, keyword_args)
        # positional_args is also a tuple.
        called_args_tuple = mock_resize_method_on_instance.call_args[0]
        
        # For an instance method call like `instance.resize(size_tuple, resample_filter)`,
        # called_args_tuple will be `(size_tuple, resample_filter)`.
        # So, called_args_tuple[1] is the resampling filter.
        actual_resampling_filter = called_args_tuple[1]
        self.assertEqual(actual_resampling_filter, Image.Resampling.BICUBIC)

        # Also check that PhotoImage was called with the result of the resize
        # self.mock_photo_image_constructor is from setUp: patch('image_viewer.ImageTk.PhotoImage', MagicMock())
        self.mock_photo_image_constructor.assert_called_with(mock_resized_result_image)


if __name__ == '__main__':
    unittest.main()
