import unittest
from unittest.mock import Mock, patch, MagicMock

# Attempt to import ImageViewer, may need to adjust sys.path if running test directly
# and image_viewer.py is not in the same directory or Python path.
try:
    from image_viewer import ImageViewer
except ImportError:
    # This is a fallback for environments where the path might not be set up,
    # e.g., if running the test script directly from a subdirectory.
    # For a proper package structure, this would not be needed.
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from image_viewer import ImageViewer


class TestImageViewerLogic(unittest.TestCase):

    def setUp(self):
        """Set up for each test method."""
        # Mock the Tkinter root window
        self.mock_root = MagicMock()
        self.mock_root.winfo_width.return_value = 800 # Default root window size
        self.mock_root.winfo_height.return_value = 600

        # Patch the Canvas and other Tkinter UI elements that ImageViewer creates internally
        # We are primarily testing logic, so full UI instantiation is not always needed
        # or can be heavily mocked.
        with patch('image_viewer.Canvas', MagicMock()) as self.mock_canvas_constructor, \
             patch('image_viewer.Menu', MagicMock()):
            # The ImageViewer instance is created with a mocked root.
            # Its internal canvas will be the MagicMock instance from the patch.
            self.viewer = ImageViewer(self.mock_root)
            self.viewer.canvas = self.mock_canvas_constructor.return_value

        # Set default canvas dimensions for tests
        self.viewer.canvas.winfo_width.return_value = 600
        self.viewer.canvas.winfo_height.return_value = 400

        # Mock the original Pillow image object
        self.mock_pil_image = MagicMock()
        self.mock_pil_image.width = 1000  # Example original image width
        self.mock_pil_image.height = 750  # Example original image height
        self.mock_pil_image.size = (self.mock_pil_image.width, self.mock_pil_image.height)
        
        # Assign this mock image to the viewer instance
        # This simulates an image having been "opened"
        self.viewer.image = self.mock_pil_image
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 0
        self.viewer.image_y = 0
        
        # Mock PhotoImage to prevent actual Tkinter PhotoImage creation errors
        # and to allow us to "inspect" what image would have been created.
        self.mock_photo_image_patch = patch('image_viewer.ImageTk.PhotoImage', MagicMock())
        self.mock_photo_image_constructor = self.mock_photo_image_patch.start()
        self.addCleanup(self.mock_photo_image_patch.stop) # Ensure patch is stopped after test

        # Mock messagebox and filedialog to prevent dialogs from popping up during tests
        self.mock_messagebox_patch = patch('image_viewer.messagebox', MagicMock())
        self.mock_messagebox = self.mock_messagebox_patch.start()
        self.addCleanup(self.mock_messagebox_patch.stop)

        self.mock_filedialog_patch = patch('image_viewer.filedialog', MagicMock())
        self.mock_filedialog = self.mock_filedialog_patch.start()
        self.addCleanup(self.mock_filedialog_patch.stop)
        
        # Ensure PIL_AVAILABLE is True for these tests,
        # otherwise some functions might return early.
        patch('image_viewer.PIL_AVAILABLE', True).start()
        self.addCleanup(patch.stopall)


    def test_initial_state_after_setup(self):
        """Test that the viewer is in the expected state after setUp."""
        self.assertEqual(self.viewer.zoom_factor, 1.0)
        self.assertEqual(self.viewer.image_x, 0)
        self.assertEqual(self.viewer.image_y, 0)
        self.assertIsNotNone(self.viewer.image)
        self.assertEqual(self.viewer.image.width, 1000)
        self.assertEqual(self.viewer.image.height, 750)

    # --- Zoom Logic Tests ---
    def create_mock_event(self, x, y, delta=0, num=0):
        """Helper to create a mock event object for zoom/pan tests."""
        event = Mock()
        event.x = x
        event.y = y
        event.delta = delta # For Windows-like scroll
        event.num = num     # For Linux-like scroll
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

    def common_crop_test_assertions(self, expected_crop_box_on_original_img):
        """
        Helper for testing save_cropped_image.
        It calls save_cropped_image and asserts the crop box.
        """
        self.mock_filedialog.asksaveasfilename.return_value = "test_save.png" # Simulate user selecting a path
        
        # Mock the image's crop method to capture arguments
        self.viewer.image.crop = MagicMock(return_value=MagicMock()) # Ensure crop returns a mock that can be saved
        
        self.viewer.save_cropped_image() # Call the method

        self.viewer.image.crop.assert_called_once()
        actual_crop_box = self.viewer.image.crop.call_args[0][0]
        self.assertEqual(actual_crop_box, expected_crop_box_on_original_img)
        self.mock_messagebox.showinfo.assert_called_once() # Assuming success

    def test_crop_no_zoom_no_pan_image_larger_than_canvas(self):
        """Image is 1000x750. Canvas is 600x400. No zoom/pan."""
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 0  # Top-left of image at canvas origin
        self.viewer.image_y = 0
        
        # Expected crop on original image: (0, 0, 600, 400)
        # scaled_vis_x1 = -0 = 0; scaled_vis_y1 = -0 = 0
        # scaled_vis_x2 = 0 + 600 = 600; scaled_vis_y2 = 0 + 400 = 400
        # orig_crop_x1 = 0 / 1.0 = 0; ...
        # final_crop_x1 = max(0,0)=0; final_crop_y1 = max(0,0)=0
        # final_crop_x2 = min(1000,600)=600; final_crop_y2 = min(750,400)=400
        self.common_crop_test_assertions((0, 0, 600, 400))

    def test_crop_with_zoom_in_no_pan(self):
        """Image 1000x750. Canvas 600x400. Zoom 2.0. Image centered by zoom logic."""
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 2.0
        # Simulate image centered after zoom (approx calculation for test setup)
        # Scaled image is 2000x1500.
        # image_x would be (600 - 2000)/2 = -700 if centered.
        # For this test, let's assume it was centered then panned a bit, or use zoom_to_cursor logic to set it.
        # If image was initially centered (at 1.0 zoom), then zoomed to 2.0 at canvas center (300,200)
        # Orig img pt under cursor: ( (300 - image_x_at_1.0)/1.0, (200 - image_y_at_1.0)/1.0 )
        # Assuming initial image_x = 0, image_y = 0 (image larger than canvas)
        # Orig img pt under cursor = (300,200)
        # self.image_x = 300 - (300 * 2.0) = 300 - 600 = -300
        # self.image_y = 200 - (200 * 2.0) = 200 - 400 = -200
        self.viewer.image_x = -300 
        self.viewer.image_y = -200
        
        # scaled_vis_x1 = -(-300) = 300
        # scaled_vis_y1 = -(-200) = 200
        # scaled_vis_x2 = -(-300) + 600 = 900
        # scaled_vis_y2 = -(-200) + 400 = 600
        # orig_crop_x1 = 300 / 2.0 = 150
        # orig_crop_y1 = 200 / 2.0 = 100
        # orig_crop_x2 = 900 / 2.0 = 450
        # orig_crop_y2 = 600 / 2.0 = 300
        # Clamping: all these are within 1000x750.
        expected_crop_box = (150, 100, 450, 300)
        self.common_crop_test_assertions(expected_crop_box)

    def test_crop_with_zoom_out_image_smaller_than_canvas(self):
        """Image 1000x750. Canvas 1200x900. Zoom 0.5. Image centered."""
        self.set_canvas_dimensions(1200, 900) # Canvas is larger
        self.viewer.zoom_factor = 0.5
        # Scaled image is 500x375.
        # Centered: image_x = (1200 - 500)/2 = 350
        # Centered: image_y = (900 - 375)/2 = 262.5 (let's use 262 for simplicity in test setup)
        self.viewer.image_x = 350
        self.viewer.image_y = 262 
        
        # scaled_vis_x1 = -350
        # scaled_vis_y1 = -262
        # scaled_vis_x2 = -350 + 1200 = 850
        # scaled_vis_y2 = -262 + 900 = 638
        # orig_crop_x1 = -350 / 0.5 = -700
        # orig_crop_y1 = -262 / 0.5 = -524
        # orig_crop_x2 = 850 / 0.5 = 1700
        # orig_crop_y2 = 638 / 0.5 = 1276
        # Clamping to original image (1000x750):
        # final_x1 = max(0, -700) = 0
        # final_y1 = max(0, -524) = 0
        # final_x2 = min(1000, 1700) = 1000
        # final_y2 = min(750, 1276) = 750
        # So, the entire original image should be saved.
        expected_crop_box = (0, 0, 1000, 750)
        self.common_crop_test_assertions(expected_crop_box)

    def test_crop_panned_right_down_zoomed(self):
        """Image 1000x750. Canvas 600x400. Zoom 1.0. Panned."""
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        # Image panned right and down. Top-left of image is now off-screen to top-left.
        self.viewer.image_x = -200 # Image's (0,0) is 200px left of canvas (0,0)
        self.viewer.image_y = -100 # Image's (0,0) is 100px above canvas (0,0)

        # scaled_vis_x1 = -(-200) = 200
        # scaled_vis_y1 = -(-100) = 100
        # scaled_vis_x2 = -(-200) + 600 = 800
        # scaled_vis_y2 = -(-100) + 400 = 500
        # orig_crop_x1 = 200 / 1.0 = 200
        # orig_crop_y1 = 100 / 1.0 = 100
        # orig_crop_x2 = 800 / 1.0 = 800
        # orig_crop_y2 = 500 / 1.0 = 500
        # Clamping: all within 1000x750.
        expected_crop_box = (200, 100, 800, 500)
        self.common_crop_test_assertions(expected_crop_box)

    def test_crop_panned_so_canvas_shows_only_background(self):
        """Image panned completely off-screen."""
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 1000 # Image starts 1000px to the right of canvas left edge
        self.viewer.image_y = 750  # Image starts 750px below canvas top edge
        # Scaled image (1000x750) is thus entirely off-canvas.
        
        # No need to call common_crop_test_assertions as it expects success.
        self.viewer.save_cropped_image()
        
        # Expect an error message, no crop, no save.
        self.mock_messagebox.showerror.assert_called_once()
        self.viewer.image.crop.assert_not_called()


    def test_crop_image_completely_within_canvas_original_size(self):
        """Image (e.g. 300x200) is smaller than canvas (600x400). No zoom/pan."""
        self.mock_pil_image.width = 300
        self.mock_pil_image.height = 200
        self.mock_pil_image.size = (300, 200)
        self.viewer.image = self.mock_pil_image # Reassign with smaller image

        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        # Assume it's centered (or placed at some x,y)
        self.viewer.image_x = 50  # Example: image placed at (50,50) on canvas
        self.viewer.image_y = 50
        
        # scaled_vis_x1 = -50
        # scaled_vis_y1 = -50
        # scaled_vis_x2 = -50 + 600 = 550
        # scaled_vis_y2 = -50 + 400 = 350
        # orig_crop_x1 = -50 / 1.0 = -50
        # orig_crop_y1 = -50 / 1.0 = -50
        # orig_crop_x2 = 550 / 1.0 = 550
        # orig_crop_y2 = 350 / 1.0 = 350
        # Clamping to image (300x200):
        # final_x1 = max(0, -50) = 0
        # final_y1 = max(0, -50) = 0
        # final_x2 = min(300, 550) = 300
        # final_y2 = min(200, 350) = 200
        # Entire image should be saved.
        expected_crop_box = (0, 0, 300, 200)
        self.common_crop_test_assertions(expected_crop_box)

    def test_crop_top_left_clamping(self):
        """Canvas view starts from negative coordinates of original image due to panning."""
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        self.viewer.image_x = 100 # Image's (0,0) is 100px to the RIGHT of canvas (0,0)
                                 # Meaning canvas (0,0) views original image's (-100, ...)
        self.viewer.image_y = 50  # Image's (0,0) is 50px BELOW canvas (0,0)

        # scaled_vis_x1 = -100
        # scaled_vis_y1 = -50
        # scaled_vis_x2 = -100 + 600 = 500
        # scaled_vis_y2 = -50 + 400 = 350
        # orig_crop_x1 = -100 / 1.0 = -100
        # orig_crop_y1 = -50 / 1.0 = -50
        # orig_crop_x2 = 500 / 1.0 = 500
        # orig_crop_y2 = 350 / 1.0 = 350
        # Clamping:
        # final_x1 = max(0, -100) = 0
        # final_y1 = max(0, -50) = 0
        # final_x2 = min(1000, 500) = 500
        # final_y2 = min(750, 350) = 350
        expected_crop_box = (0, 0, 500, 350)
        self.common_crop_test_assertions(expected_crop_box)

    def test_crop_bottom_right_clamping(self):
        """Canvas view extends beyond original image boundaries."""
        self.set_canvas_dimensions(600, 400)
        self.viewer.zoom_factor = 1.0
        # Image (1000x750) panned so its bottom-right is visible
        # Let image_x be such that canvas right edge is beyond image right edge.
        # Image right edge on canvas = image_x + 1000 * 1.0
        # We want canvas_width (600) > image_x + 1000. This is not right.
        # We want: image_x + image_width_scaled > canvas_width, but part of canvas sees beyond.
        # Example: image_x = 450. Image width 1000. image_x + 1000 = 1450. Canvas 600.
        # This means canvas shows from 450 to 1050 of the scaled image (which is 0 to 600 on canvas).
        # But we want the opposite: canvas shows beyond the image.
        # Let image_x = -800. Scaled image starts at -800 on canvas. Its right edge is at -800 + 1000 = 200.
        # Canvas (600x400) shows scaled image from x: (0 - (-800)) = 800 up to (600 - (-800)) = 1400
        # So, canvas wants to see original image from 800 to 1400.
        self.viewer.image_x = -800 # Scaled image's (0,0) is far left of canvas.
        self.viewer.image_y = -600 # Scaled image's (0,0) is far up of canvas.

        # scaled_vis_x1 = -(-800) = 800
        # scaled_vis_y1 = -(-600) = 600
        # scaled_vis_x2 = 800 + 600 = 1400
        # scaled_vis_y2 = 600 + 400 = 1000
        # orig_crop_x1 = 800 / 1.0 = 800
        # orig_crop_y1 = 600 / 1.0 = 600
        # orig_crop_x2 = 1400 / 1.0 = 1400
        # orig_crop_y2 = 1000 / 1.0 = 1000
        # Clamping to original image (1000x750):
        # final_x1 = max(0, 800) = 800
        # final_y1 = max(0, 600) = 600
        # final_x2 = min(1000, 1400) = 1000
        # final_y2 = min(750, 1000) = 750
        expected_crop_box = (800, 600, 1000, 750) # This is a 200x150 crop from bottom right.
        self.common_crop_test_assertions(expected_crop_box)


if __name__ == '__main__':
    unittest.main()
