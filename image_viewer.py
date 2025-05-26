import tkinter as tk
from tkinter import filedialog, Menu, Canvas, messagebox
import os
from datetime import datetime
import math # Added for rotation calculations
try:
    from PIL import ImageTk, Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    # Inform the user if Pillow is not installed, as image features will be disabled.
    print("Pillow library not found. Image opening functionality will be disabled.")

# Constants for proxy image handling
PROXY_CREATION_THRESHOLD_DIM = 6000  # If max(width, height) > this, create proxy
PROXY_MAX_TARGET_DIM = 3000        # Proxy's max dimension (target for proxy)
ROTATION_INCREMENT = 5.0           # Degrees for each rotation step
# Animation Constants
ANIMATION_DURATION_MS = 200  # Total duration of zoom animation
ANIMATION_TOTAL_STEPS = 10   # Number of frames in the animation


class ImageViewer:
    """
    A simple image viewer application built with Tkinter and Pillow.

    Supports opening various image formats, zooming with the mouse wheel
    (centered on the cursor), panning by dragging the image, and saving
    the currently visible portion of the image.
    """
    def __init__(self, master):
        """
        Initialize the ImageViewer application.

        Args:
            master: The root Tkinter window.
        """
        self.master = master

        # Attempt to set true fullscreen first, then make it borderless.
        # If this specific order causes a TclError on some systems, fallback.
        try:
            self.master.attributes('-fullscreen', True)
            self.master.overrideredirect(True) 
            print("Successfully set fullscreen then overrideredirect.") # Temporary log
        except tk.TclError as e:
            print(f"TclError with fullscreen then overrideredirect: {e}") # Temporary log
            # Fallback to previous manual geometry method if the above fails
            self.master.overrideredirect(True) # Ensure borderless
            screen_width = self.master.winfo_screenwidth()
            screen_height = self.master.winfo_screenheight()
            self.master.geometry(f"{screen_width}x{screen_height}+0+0")
            print("Fell back to manual geometry for fullscreen effect.") # Temporary log
        
        # master.title("Image Viewer") # Title is not visible in borderless fullscreen

        # --- Application State ---
        self.image = None  # Stores the working Pillow Image object (original or proxy).
        self.original_image = None # Stores the true original Pillow Image object.
        self.original_width = 0    # Width of the true original image.
        self.original_height = 0   # Height of the true original image.
        self.tk_image = None # Stores the PhotoImage object for display on canvas (kept to avoid garbage collection).
        self.zoom_factor = 1.0  # Current zoom level of the image.
        self.image_x = 0  # Top-left x-coordinate of the image on the canvas.
        self.image_y = 0  # Top-left y-coordinate of the image on the canvas.
        self.image_on_canvas = None # ID of the image item on the canvas.
        self.image_path = None # Path to the currently loaded image.
        self.zoom_debounce_timer = None # Timer for debouncing zoom operations
        self.resize_debounce_timer = None # Timer for debouncing window resize fitting
        self.image_list = [] # List of image files in the current directory
        self.current_image_index = -1 # Index of the current image in image_list
        self.is_zoomed_to_original_size = False # State for double-click zoom
        self.current_rotation_angle = 0.0 # Current rotation angle of the image
        self.rotation_debounce_timer = None # Timer for debouncing rotation operations

        # --- Animation State ---
        self.animation_timer_id = None  # For cancelling ongoing animation frame
        self.anim_start_zoom = 0.0
        self.anim_start_x = 0.0
        self.anim_start_y = 0.0
        self.anim_target_zoom = 0.0 # Target for the current animation segment
        self.anim_target_x = 0.0
        self.anim_target_y = 0.0
        self.anim_current_step = 0

        # --- Panning State ---
        self.drag_start_x = 0  # Mouse x-coordinate at the start of a pan.
        self.drag_start_y = 0  # Mouse y-coordinate at the start of a pan.
        self.dragging = False  # True if a pan operation is in progress.

        # --- UI Elements ---
        # Create a Canvas widget for image display.
        self.canvas = Canvas(master, bg="black", cursor="arrow") # Changed background to black
        self.canvas.pack(fill="both", expand=True) # Make canvas fill the window.

        # --- Event Bindings ---
        # Bind mouse wheel events for zooming.
        self.canvas.bind("<MouseWheel>", self.zoom_image)  # Windows
        self.canvas.bind("<Button-4>", self.zoom_image)    # Linux/macOS scroll up
        self.canvas.bind("<Button-5>", self.zoom_image)    # Linux/macOS scroll down

        # Bind mouse events for panning.
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.pan_image)
        self.canvas.bind("<ButtonRelease-1>", self.stop_pan)
        # Bind double-click for zoom toggle
        self.canvas.bind('<Double-Button-1>', self.handle_double_click_zoom)
        # Bind Shift+MouseWheel for rotation
        self.canvas.bind('<Shift-MouseWheel>', self.handle_rotate_event)

        # --- Menu Bar Removed ---
        # menubar = Menu(master)
        # filemenu = Menu(menubar, tearoff=0)
        # filemenu.add_command(label="Open...", command=self.open_image, state=tk.NORMAL if PIL_AVAILABLE else tk.DISABLED)
        # filemenu.add_separator()
        # filemenu.add_command(label="Exit", command=master.quit) # Exit is now handled by Escape key
        # menubar.add_cascade(label="File", menu=filemenu)
        # master.config(menu=menubar)

        # Bind Ctrl+S for saving the cropped/visible part of the image.
        master.bind('<Control-s>', self.save_cropped_image)

        # Bind Left/Right arrow keys for image navigation (handler to be implemented)
        master.bind('<Left>', self.handle_arrow_key_event)
        master.bind('<Right>', self.handle_arrow_key_event)
        # Bind window resize event
        master.bind('<Configure>', self.handle_window_resize)
        # Bind Ctrl+O to open_image method
        master.bind('<Control-o>', lambda event: self.open_image())
        # Bind Escape key to exit application
        master.bind('<Escape>', self.handle_escape_key)

    def _fit_image_to_canvas(self, target_canvas_width=None, target_canvas_height=None):
        """
        Calculates zoom_factor, image_x, and image_y to fit the current image
        into the target canvas dimensions and centers it.

        Args:
            target_canvas_width (int, optional): The width to fit into. Defaults to current canvas width.
            target_canvas_height (int, optional): The height to fit into. Defaults to current canvas height.
        
        Returns:
            bool: True if fitting was calculated, False otherwise (e.g., no image).
        """
        if not self.image:
            return False

        if target_canvas_width is None:
            target_canvas_width = self.canvas.winfo_width()
        if target_canvas_height is None:
            target_canvas_height = self.canvas.winfo_height()

        base_image_for_dims = self.image # This is the proxy or original

        if self.current_rotation_angle != 0.0:
            # Get dimensions of the maximal_inner_rect of the base_image_for_dims when rotated
            # The _calculate_maximal_inner_rect returns (left, top, right, bottom) of the crop
            # relative to the expanded rotated image. For fitting, we need the width/height of this rect.
            # The actual dimensions of the crop are calculated based on the *original* (pre-rotation)
            # dimensions of the image that was rotated.
            crop_l, crop_t, crop_r, crop_b = self._calculate_maximal_inner_rect(
                base_image_for_dims.width, 
                base_image_for_dims.height, 
                self.current_rotation_angle
            )
            # The effective width and height for fitting is the size of this inner rectangle
            img_width = crop_r - crop_l
            img_height = crop_b - crop_t
            
            # Ensure dimensions are at least 1 for valid calculations
            img_width = max(1, img_width)
            img_height = max(1, img_height)
        else:
            img_width, img_height = base_image_for_dims.size


        if img_width <= 0 or img_height <= 0 or target_canvas_width <= 0 or target_canvas_height <= 0:
            self.zoom_factor = 1.0
        else:
            width_ratio = target_canvas_width / img_width
            height_ratio = target_canvas_height / img_height
            self.zoom_factor = min(width_ratio, height_ratio)
            if self.zoom_factor <= 0: # Fallback, should not happen with positive dimensions
                self.zoom_factor = 1.0
        
        new_width = int(img_width * self.zoom_factor)
        new_height = int(img_height * self.zoom_factor)

        self.image_x = (target_canvas_width - new_width) / 2
        self.image_y = (target_canvas_height - new_height) / 2
        return True

    def open_image(self, filepath=None): # Modified to accept optional filepath
        """
        Open an image file, display it on the canvas, and reset view.

        If `filepath` is None, shows a file dialog for the user to select an image.
        Otherwise, attempts to load the image from the given `filepath`.
        If an image is selected/provided and loaded, it's fitted to window,
        and the current directory is scanned for other images.
        """
        if not PIL_AVAILABLE:
            messagebox.showerror("Error", "Pillow library is not installed. Image opening functionality is disabled.")
            return

        if filepath is None: # Only show dialog if no path is provided
            filepath = filedialog.askopenfilename(
                title="Open Image",
                filetypes=[
                    ('Image Files', ('*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp')),
                    ('PNG files', '*.png'),
                    ('JPEG files', ('*.jpg', '*.jpeg')),
                    ('GIF files', '*.gif'),
                    ('BMP files', '*.bmp'),
                    ('All files', '*.*')
                ]
            )
        
        if not filepath: # If no filepath from dialog or was initially None
            return

        try:
            # Attempt to open the image using Pillow.
            pil_img = Image.open(filepath) # Load into a local variable first
            
            self.original_image = pil_img
            self.original_width, self.original_height = self.original_image.size
            self.image = self.original_image # Default to using original

            # Proxy Creation Logic
            if self.original_width > PROXY_CREATION_THRESHOLD_DIM or \
               self.original_height > PROXY_CREATION_THRESHOLD_DIM:
                
                if self.original_width > self.original_height:
                    scale_factor = PROXY_MAX_TARGET_DIM / self.original_width
                    proxy_width = PROXY_MAX_TARGET_DIM
                    proxy_height = int(self.original_height * scale_factor)
                else:
                    scale_factor = PROXY_MAX_TARGET_DIM / self.original_height
                    proxy_height = PROXY_MAX_TARGET_DIM
                    proxy_width = int(self.original_width * scale_factor)

                proxy_width = max(1, proxy_width)
                proxy_height = max(1, proxy_height)

                try:
                    print(f"Creating proxy: original ({self.original_width}x{self.original_height}), proxy ({proxy_width}x{proxy_height})")
                    self.image = self.original_image.resize((proxy_width, proxy_height), Image.Resampling.BICUBIC)
                except Exception as e:
                    print(f"Error creating proxy: {e}")
                    self.image = self.original_image # Fallback to original
            else:
                print(f"Using original image: ({self.original_width}x{self.original_height})")
                pass # self.image already points to self.original_image

            # Normalize and store the image path (using the original filepath)
            self.image_path = os.path.normcase(os.path.abspath(filepath))
            
            # Fit image to window initially using the new helper method
            # This will now use self.image (which could be the proxy)
            self.master.update_idletasks() # Ensure canvas dimensions are current before fitting
            if self._fit_image_to_canvas(): # _fit_image_to_canvas uses self.image.size
                self.is_zoomed_to_original_size = False
            self.current_rotation_angle = 0.0 # Reset rotation for new image
            
            # Scan directory for other images
            current_dir = os.path.dirname(self.image_path)
            valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
            try:
                all_files_in_dir = os.listdir(current_dir)
                self.image_list = sorted([
                    os.path.normcase(os.path.abspath(os.path.join(current_dir, f)))
                    for f in all_files_in_dir
                    if os.path.isfile(os.path.join(current_dir, f)) and \
                       f.lower().endswith(valid_extensions)
                ])
            except OSError: # Handle potential permission errors etc.
                self.image_list = []
            
            if self.image_list:
                try:
                    self.current_image_index = self.image_list.index(self.image_path)
                except ValueError:
                    # Should not happen if image_path was found by listdir, but as a fallback
                    self.image_list = [] # Invalidate list if current path not in it
                    self.current_image_index = -1
            else:
                self.current_image_index = -1

            self.update_display()

        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {filepath}")
            self.image = None
            self.original_image = None
            self.original_width = 0
            self.original_height = 0
            self.image_path = None # Reset path on failure
            self.image_list = []
            self.current_image_index = -1
            self.current_rotation_angle = 0.0
        except Exception as e:
            # Catch other potential Pillow errors (e.g., unrecognized format, truncated file)
            # Use original filepath for error message before it's normalized
            messagebox.showerror("Error Opening Image", f"Could not open or read image file:\n{filepath if filepath else 'Unknown'}\n\nDetails: {e}")
            self.image = None
            self.original_image = None
            self.original_width = 0
            self.original_height = 0
            self.image_path = None # Reset path on failure
            self.image_list = []
            self.current_image_index = -1
            self.current_rotation_angle = 0.0

    def update_display(self):
        """
        Redraw the image on the canvas based on current zoom and position.

        This method resizes the original image according to `self.zoom_factor`,
        then creates a new PhotoImage and places it on the canvas at
        `(self.image_x, self.image_y)`.
        """
        if self.image is None: 
            return 

        base_image_to_process = self.image # This is the proxy or original

        image_after_rotation_expanded = base_image_to_process
        if self.current_rotation_angle != 0.0:
            try:
                image_after_rotation_expanded = base_image_to_process.rotate(
                    -self.current_rotation_angle, 
                    resample=Image.Resampling.NEAREST, 
                    expand=True
                )
            except Exception as e:
                print(f"Error during rotation: {e}")
                # Fallback to using the base image if rotation fails
        
        image_to_be_zoomed = image_after_rotation_expanded # Default if no rotation or crop fails

        if self.current_rotation_angle != 0.0:
            # Auto-crop the expanded rotated image to the maximal inner rectangle
            # The calculation needs the *pre-rotation* dimensions of the image that was rotated (base_image_to_process)
            crop_l, crop_t, crop_r, crop_b = self._calculate_maximal_inner_rect(
                base_image_to_process.width, 
                base_image_to_process.height, 
                self.current_rotation_angle
            )
            
            if (crop_r - crop_l) >= 1 and (crop_b - crop_t) >= 1:
                try:
                    image_to_be_zoomed = image_after_rotation_expanded.crop((crop_l, crop_t, crop_r, crop_b))
                except Exception as e:
                    print(f"Error during auto-crop: {e}")
                    # Fallback if crop fails, use expanded rotated image
            elif image_after_rotation_expanded.width == 0 or image_after_rotation_expanded.height == 0:
                 image_to_be_zoomed = Image.new("RGBA", (1,1), (0,0,0,0)) # Placeholder for safety

        # Dimensions for zoom calculation are now from the (potentially cropped) image_to_be_zoomed
        current_display_width, current_display_height = image_to_be_zoomed.size
        if current_display_width == 0 or current_display_height == 0: # Safety for resize
            current_display_width = max(1, current_display_width)
            current_display_height = max(1, current_display_height)
            # If dimensions became zero (e.g. due to bad crop result), use a placeholder
            image_to_be_zoomed = Image.new("RGBA", (current_display_width, current_display_height), (0,0,0,0))

        # Calculate Scaled Dimensions (Zoom) based on the (potentially rotated and cropped) image
        scaled_width = int(current_display_width * self.zoom_factor)
        scaled_height = int(current_display_height * self.zoom_factor)
        scaled_width = max(1, scaled_width) # Ensure at least 1x1
        scaled_height = max(1, scaled_height)

        try:
            # Resize for Display
            image_to_render = image_to_be_zoomed.resize(
                (scaled_width, scaled_height), 
                Image.Resampling.NEAREST # Consistent with zoom quality
            )
            
            self.tk_image = ImageTk.PhotoImage(image_to_render)

            if self.image_on_canvas:
                self.canvas.itemconfig(self.image_on_canvas, image=self.tk_image)
                self.canvas.coords(self.image_on_canvas, self.image_x, self.image_y)
            else:
                self.image_on_canvas = self.canvas.create_image(
                    self.image_x, self.image_y, anchor="nw", image=self.tk_image, tags="image_tag"
                )
        except Exception as e:
            messagebox.showerror("Error Updating Display", f"An error occurred while updating the image display: {e}")
            # Consider resetting image or state if display fails critically
            # self.image = None 
            # self.image_on_canvas = None


    def zoom_image(self, event):
        """
        Handle mouse wheel scrolling to zoom the image.

        Zooms in or out based on the scroll direction. The zoom is centered
        around the mouse cursor's position on the image.

        Args:
            event: The Tkinter event object (e.g., from <MouseWheel> binding).
                   Contains `event.delta` (Windows) or `event.num` (Linux/macOS)
                   for scroll direction, and `event.x`, `event.y` for cursor position.
        """
        if self.image is None:
            return 
        
        self.is_zoomed_to_original_size = False # Any scroll zoom overrides double-click state

        # Cancel any ongoing animation frame timer from previous zoom events
        if self.animation_timer_id:
            self.master.after_cancel(self.animation_timer_id)
            self.animation_timer_id = None
            # When animation is cancelled, current self.zoom_factor, self.image_x, self.image_y
            # will reflect the last rendered frame of that animation. These become the start
            # for the new animation calculation initiated by the new scroll.

        # Store current state as potential start for animation if debounce doesn't cancel this
        current_zoom_factor = self.zoom_factor
        current_image_x = self.image_x
        current_image_y = self.image_y

        zoom_step = 0.1 
        
        # Calculate target zoom factor based on scroll direction
        target_zoom_factor = current_zoom_factor # Start with current
        if event.num == 4 or event.delta > 0:
            target_zoom_factor *= (1 + zoom_step)
        elif event.num == 5 or event.delta < 0:
            target_zoom_factor *= (1 - zoom_step)
        else:
            return
        
        target_zoom_factor = max(0.1, min(target_zoom_factor, 5.0))

        # Calculate target image position (zoom towards cursor)
        mouse_x = event.x
        mouse_y = event.y
        
        # Point on the *working* image under the mouse before this proposed zoom
        # Use `current_zoom_factor` because that's what's currently displayed
        img_coord_x = (mouse_x - current_image_x) / current_zoom_factor
        img_coord_y = (mouse_y - current_image_y) / current_zoom_factor
        
        # Calculate new top-left to keep this point under the cursor with `target_zoom_factor`
        self.anim_target_zoom = target_zoom_factor
        self.anim_target_x = mouse_x - (img_coord_x * self.anim_target_zoom)
        self.anim_target_y = mouse_y - (img_coord_y * self.anim_target_zoom)

        # Debounce the start of the animation
        if self.zoom_debounce_timer:
            self.master.after_cancel(self.zoom_debounce_timer)
        
        self.zoom_debounce_timer = self.master.after(100, self._perform_zoom_update)

    def _perform_zoom_update(self):
        """
        Called by the zoom debounce timer. Initiates the zoom animation.
        """
        if not self.image:
            return
        self.zoom_debounce_timer = None 

        # If there's an old animation running, ensure it's stopped.
        if self.animation_timer_id:
            self.master.after_cancel(self.animation_timer_id)
            self.animation_timer_id = None

        # Setup for the new animation sequence
        self.anim_start_zoom = self.zoom_factor 
        self.anim_start_x = self.image_x
        self.anim_start_y = self.image_y
        # Targets (self.anim_target_zoom, _x, _y) are already set by the last call to zoom_image
        
        self.anim_current_step = 0
        self._animate_zoom_frame() 

    def _animate_zoom_frame(self):
        """
        Performs a single frame of the zoom animation.
        """
        self.anim_current_step += 1
        progress = self.anim_current_step / ANIMATION_TOTAL_STEPS

        if self.anim_current_step >= ANIMATION_TOTAL_STEPS:
            self.zoom_factor = self.anim_target_zoom
            self.image_x = self.anim_target_x
            self.image_y = self.anim_target_y
            self.animation_timer_id = None
            if self.zoom_factor == 1.0: # Check if it's 100% zoom
                 # This might need adjustment if fit-to-window can also result in zoom_factor 1.0
                 # For now, assume only direct 100% zoom sets this.
                 # self.is_zoomed_to_original_size = True # State update for double-click
                 pass # is_zoomed_to_original_size is managed by handle_double_click_zoom and zoom_image
        else:
            # Interpolate
            self.zoom_factor = self.anim_start_zoom + \
                               (self.anim_target_zoom - self.anim_start_zoom) * progress
            self.image_x = self.anim_start_x + \
                           (self.anim_target_x - self.anim_start_x) * progress
            self.image_y = self.anim_start_y + \
                           (self.anim_target_y - self.anim_start_y) * progress
            
            delay_per_frame = ANIMATION_DURATION_MS // ANIMATION_TOTAL_STEPS
            self.animation_timer_id = self.master.after(delay_per_frame, self._animate_zoom_frame)

        self.update_display() # Render this frame

    def start_pan(self, event):
        """
        Begin a pan operation when the left mouse button is pressed.

        Stores the initial mouse position and changes the cursor to "fleur".

        Args:
            event: The Tkinter event object from <ButtonPress-1>.
        """
        if self.image is None: # Do not pan if no image is loaded.
            return
        self.drag_start_x = event.x  # Record mouse x at drag start.
        self.drag_start_y = event.y  # Record mouse y at drag start.
        self.dragging = True         # Set dragging flag.
        self.canvas.config(cursor="fleur") # Change cursor to indicate panning.

    def pan_image(self, event):
        """
        Pan the image as the mouse is dragged with the left button down.

        Calculates the delta of mouse movement and updates the image's
        position on the canvas (`self.image_x`, `self.image_y`).

        Args:
            event: The Tkinter event object from <B1-Motion>.
        """
        if self.dragging and self.image: # Only pan if dragging and image exists.
            dx = event.x - self.drag_start_x # Change in mouse x.
            dy = event.y - self.drag_start_y # Change in mouse y.
            
            # Update image's top-left coordinates on the canvas.
            self.image_x += dx
            self.image_y += dy
            
            # Update drag start coordinates for the next motion event (ensures continuous panning).
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            
            # Directly move the existing image item on the canvas for performance.
            if self.image_on_canvas:
                self.canvas.coords(self.image_on_canvas, self.image_x, self.image_y)
            else:
                # Fallback or if image_on_canvas was somehow lost, though unlikely with current logic
                self.update_display() 

    def stop_pan(self, event):
        """
        End the pan operation when the left mouse button is released.

        Resets the dragging flag and changes the cursor back to "arrow".

        Args:
            event: The Tkinter event object from <ButtonRelease-1>.
        """
        self.dragging = False # Clear dragging flag.
        self.canvas.config(cursor="arrow") # Reset cursor to default.

    def save_cropped_image(self, event=None):
        """
        Save the currently visible portion of the image to a file.

        Triggered by Ctrl+S. Calculates the region of the original image
        that is visible on the canvas, prompts the user for a save location,
        and saves the cropped image.

        Args:
            event: The Tkinter event object (optional, for key binding).
        """
        if not self.original_image: # Check for the original image first
            messagebox.showinfo("No Image", "No image loaded to save.")
            return

        if not PIL_AVAILABLE:
            messagebox.showerror("Error", "Pillow library is not available. Cannot save images.")
            return

        if not self.image_path: # Original image path is needed for saving location
            messagebox.showerror("Error", "Original image path is not known. Cannot determine save location.")
            return

        # Get current dimensions of the canvas.
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # --- Calculate Crop Coordinates ---
        # 1. Visible region on the *zoomed working image* (self.image), in its own coordinate system.
        #    (self.image_x, self.image_y) is the top-left of the zoomed working image on the canvas.
        #    So, (0,0) on canvas corresponds to (-self.image_x, -self.image_y) on the zoomed working image.
        vis_x1_on_working_img_scaled = -self.image_x
        vis_y1_on_working_img_scaled = -self.image_y
        vis_x2_on_working_img_scaled = -self.image_x + canvas_width
        vis_y2_on_working_img_scaled = -self.image_y + canvas_height
        
        # 2. Convert these coordinates to the *unzoomed working image's* coordinate system.
        crop_x1_on_working_img = vis_x1_on_working_img_scaled / self.zoom_factor
        crop_y1_on_working_img = vis_y1_on_working_img_scaled / self.zoom_factor
        crop_x2_on_working_img = vis_x2_on_working_img_scaled / self.zoom_factor
        crop_y2_on_working_img = vis_y2_on_working_img_scaled / self.zoom_factor

        # 3. Translate coordinates from working image to original image if a proxy is in use.
        final_crop_x1_on_original = crop_x1_on_working_img
        final_crop_y1_on_original = crop_y1_on_working_img
        final_crop_x2_on_original = crop_x2_on_working_img
        final_crop_y2_on_original = crop_y2_on_working_img

        if self.image is not self.original_image: # Check if proxy is active
            if self.image.width > 0 and self.image.height > 0: # Avoid division by zero for proxy
                scale_to_original_x = self.original_width / self.image.width
                scale_to_original_y = self.original_height / self.image.height

                final_crop_x1_on_original = crop_x1_on_working_img * scale_to_original_x
                final_crop_y1_on_original = crop_y1_on_working_img * scale_to_original_y
                final_crop_x2_on_original = crop_x2_on_working_img * scale_to_original_x
                final_crop_y2_on_original = crop_y2_on_working_img * scale_to_original_y
            # else: if proxy dimensions are zero, something is very wrong. 
            #       Proceeding with unscaled coords is unlikely to be correct but avoids crash here.
            #       Clamping later should handle this.

        # 4. Clamp these coordinates to the boundaries of the *original* image.
        clamped_crop_x1 = max(0, final_crop_x1_on_original)
        clamped_crop_y1 = max(0, final_crop_y1_on_original)
        clamped_crop_x2 = min(self.original_width, final_crop_x2_on_original)
        clamped_crop_y2 = min(self.original_height, final_crop_y2_on_original)
        
        # 5. Validate the final crop box on the original image.
        #    Ensure coordinates are integers for Pillow's crop method.
        final_box_for_original = (
            int(round(clamped_crop_x1)),
            int(round(clamped_crop_y1)),
            int(round(clamped_crop_x2)),
            int(round(clamped_crop_y2))
        )
        
        # Check if the calculated crop box has a valid (positive) width and height
        if final_box_for_original[0] >= final_box_for_original[2] or \
           final_box_for_original[1] >= final_box_for_original[3]:
            messagebox.showerror("Error", "No part of the image is visible to save, or the visible area is invalid.")
            return

        # --- Construct New File Path ---
        directory = os.path.dirname(self.image_path)
        basename_full = os.path.basename(self.image_path)
        basename, extension = os.path.splitext(basename_full)
        
        if not extension: # Handle filenames without a dot or empty extension
            extension = ".png" # Default to .png if no extension
        
        timestamp = datetime.now().strftime("_%Y%m%d%H%M%S")
        new_filename = f"{basename}{timestamp}{extension}"
        new_filepath = os.path.join(directory, new_filename)

        # --- Save the Image ---
        try:
            cropped_image = self.original_image.crop(final_box_for_original)
            cropped_image.save(new_filepath)
            messagebox.showinfo("Success", f"Cropped image saved as\n{new_filepath}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save image: {e}")

    def handle_arrow_key_event(self, event):
        """
        Handles Left and Right arrow key presses for image navigation.
        """
        if not self.image_list: # No list of images to navigate
            return

        direction = 0
        if event.keysym == 'Left':
            direction = -1
        elif event.keysym == 'Right':
            direction = 1 # Corrected to +1
        else: # Should not happen if bindings are specific
            return

        if direction != 0:
            self._load_adjacent_image(direction)

    def _load_adjacent_image(self, direction):
        """
        Loads the next or previous image in the `self.image_list`.

        Args:
            direction (int): -1 for previous, +1 for next.
        """
        if not self.image_list or self.current_image_index == -1:
            # No image list or current image not properly identified in the list
            return

        new_index = self.current_image_index + direction

        if 0 <= new_index < len(self.image_list):
            # Check if the new image is different from the current one
            if new_index != self.current_image_index: # This also implicitly checks if new_index is same as current
                new_image_path = self.image_list[new_index]
                # self.open_image will handle loading, display, and also
                # re-scanning the directory and updating self.image_list and self.current_image_index.
                self.open_image(filepath=new_image_path)
        # else:
            # Optional: Provide feedback if at the start/end of the list
            # For example, using tkinter.messagebox.showinfo or a status bar
            # print(f"At {'start' if direction == -1 else 'end'} of image list.")
            # By default, do nothing if out of bounds (no wrapping around)

    def handle_rotate_event(self, event):
        if not self.image:
            return

        # Cancel any pending rotation update
        if self.rotation_debounce_timer:
            self.master.after_cancel(self.rotation_debounce_timer)

        # Determine rotation direction and update angle
        increment_sign = 0
        # For Linux, event.num 4 is scroll up, 5 is scroll down (like MouseWheel)
        # For Windows, event.delta is positive for scroll up, negative for scroll down
        if event.num == 4 or event.delta > 0: # Typically scroll up / away from user
            increment_sign = 1  # Clockwise
        elif event.num == 5 or event.delta < 0: # Typically scroll down / towards user
            increment_sign = -1 # Counter-clockwise
        
        if increment_sign != 0:
            self.current_rotation_angle = (self.current_rotation_angle + (increment_sign * ROTATION_INCREMENT)) % 360.0
            # print(f"New angle: {self.current_rotation_angle}") # Temporary log

        self.rotation_debounce_timer = self.master.after(150, self._perform_rotation_update) # 150ms delay

    def _perform_rotation_update(self):
        if not self.image:
            return
        self.rotation_debounce_timer = None
        print(f"PERFORMING ROTATION UPDATE: Angle {self.current_rotation_angle}") # Placeholder log
        # In the next step, this will call a modified update_display or similar
        # For now, to ensure it uses the new angle, we can call update_display
        # update_display will need to be modified to use self.current_rotation_angle
        self.update_display() # This will be the subject of the next plan step

    def handle_window_resize(self, event):
        """
        Handles the window resize event (<Configure>).
        Debounces the actual refitting logic to avoid excessive updates.
        """
        # Check if the event is for the master window itself, not a child widget's configure event
        # This check might be redundant if only master is bound, but good for safety.
        if event.widget != self.master:
            return

        if self.resize_debounce_timer:
            self.master.after_cancel(self.resize_debounce_timer)
        
        self.resize_debounce_timer = self.master.after(200, self._perform_fit_to_window_update) # 200ms delay

    def _perform_fit_to_window_update(self):
        """
        Called by the resize debounce timer.
        Refits the image to the current canvas size and updates the display.
        """
        self.resize_debounce_timer = None
        if self.image:
            if self._fit_image_to_canvas(): # This updates zoom_factor, image_x, image_y
                self.is_zoomed_to_original_size = False # Reset on fit-to-window
                self.update_display()

    def handle_double_click_zoom(self, event):
        """
        Toggles zoom between fit-to-window and 100% (original size) centered at cursor.
        """
        if not self.image:
            return

        # Cancel any ongoing zoom animation or debounce timers
        if self.animation_timer_id:
            self.master.after_cancel(self.animation_timer_id)
            self.animation_timer_id = None
        if self.zoom_debounce_timer:
            self.master.after_cancel(self.zoom_debounce_timer)
            self.zoom_debounce_timer = None

        self.anim_start_zoom = self.zoom_factor
        self.anim_start_x = self.image_x
        self.anim_start_y = self.image_y

        if not self.is_zoomed_to_original_size:
            # Target: 100% zoom, centered at cursor
            target_zoom = 1.0
            # Calculate point on working image under cursor
            img_coord_x = (event.x - self.image_x) / self.zoom_factor
            img_coord_y = (event.y - self.image_y) / self.zoom_factor
            
            self.anim_target_zoom = target_zoom
            self.anim_target_x = event.x - (img_coord_x * self.anim_target_zoom)
            self.anim_target_y = event.y - (img_coord_y * self.anim_target_zoom)
            self.is_zoomed_to_original_size = True # Set state based on *target*
        else:
            # Target: Fit-to-window
            # Store current canvas dimensions before calling _fit_image_to_canvas
            # as it might use winfo_width/height if not provided.
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # _fit_image_to_canvas calculates and sets self.zoom_factor, self.image_x, self.image_y
            # We need to capture these as targets.
            temp_zoom = self.zoom_factor # Store current to restore if fit fails
            temp_x = self.image_x
            temp_y = self.image_y
            
            if self._fit_image_to_canvas(target_canvas_width=canvas_width, target_canvas_height=canvas_height):
                self.anim_target_zoom = self.zoom_factor
                self.anim_target_x = self.image_x
                self.anim_target_y = self.image_y
                self.is_zoomed_to_original_size = False # Set state based on *target*
            else: # Fit failed, revert to current state as target (no animation)
                self.anim_target_zoom = temp_zoom
                self.anim_target_x = temp_x
                self.anim_target_y = temp_y
                # is_zoomed_to_original_size remains True
                return # No animation if fit failed
            
            # Restore actual current state for anim_start values
            self.zoom_factor = self.anim_start_zoom
            self.image_x = self.anim_start_x
            self.image_y = self.anim_start_y
        
        self.anim_current_step = 0
        self._animate_zoom_frame()

    def handle_escape_key(self, event=None):
        """
        Handles the Escape key press to exit the application.
        """
        # print("Escape key pressed. Exiting application.") # Optional: for logging
        self.master.destroy()


# --- Main Application Setup ---
if __name__ == '__main__':
    # Create the main Tkinter window.
    root = tk.Tk()
    # Create an instance of the ImageViewer application, passing the root window.
    app = ImageViewer(root)
    # Ensure the main window has a defined initial size for consistent UI behavior (e.g., initial centering).
    root.geometry("800x600") 
    # Start the Tkinter event loop to run the application.
    root.mainloop()
