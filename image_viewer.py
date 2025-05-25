import tkinter as tk
from tkinter import filedialog, Menu, Canvas, messagebox
try:
    from PIL import ImageTk, Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    # Inform the user if Pillow is not installed, as image features will be disabled.
    print("Pillow library not found. Image opening functionality will be disabled.")

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
        master.title("Image Viewer")

        # --- Application State ---
        self.image = None  # Stores the original Pillow Image object.
        self.tk_image = None # Stores the PhotoImage object for display on canvas (kept to avoid garbage collection).
        self.zoom_factor = 1.0  # Current zoom level of the image.
        self.image_x = 0  # Top-left x-coordinate of the image on the canvas.
        self.image_y = 0  # Top-left y-coordinate of the image on the canvas.
        self.image_on_canvas = None # ID of the image item on the canvas.

        # --- Panning State ---
        self.drag_start_x = 0  # Mouse x-coordinate at the start of a pan.
        self.drag_start_y = 0  # Mouse y-coordinate at the start of a pan.
        self.dragging = False  # True if a pan operation is in progress.

        # --- UI Elements ---
        # Create a Canvas widget for image display.
        self.canvas = Canvas(master, bg="white", cursor="arrow") # Default cursor is an arrow.
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

        # Create a menu bar.
        menubar = Menu(master)
        filemenu = Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open...", command=self.open_image, state=tk.NORMAL if PIL_AVAILABLE else tk.DISABLED)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=master.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        master.config(menu=menubar)

        # Bind Ctrl+S for saving the cropped/visible part of the image.
        master.bind('<Control-s>', self.save_cropped_image)

    def open_image(self):
        """
        Open an image file, display it on the canvas, and reset view.

        Shows a file dialog for the user to select an image.
        If an image is selected, it's loaded, centered, and displayed.
        Zoom and pan are reset to default.
        """
        if not PIL_AVAILABLE:
            messagebox.showerror("Error", "Pillow library is not installed. Image opening functionality is disabled.")
            return

        filepath = filedialog.askopenfilename(
            title="Open Image",
            filetypes=(
                ("PNG files", "*.png"),
                ("JPG files", "*.jpg;*.jpeg"),
                ("GIF files", "*.gif"),
                ("BMP files", "*.bmp"),
                ("All files", "*.*")
            )
        )
        if not filepath:
            return

        try:
            # Attempt to open the image using Pillow.
            self.image = Image.open(filepath)
            
            # Reset zoom factor and image position for the new image.
            self.zoom_factor = 1.0
            
            # Center the image on the canvas.
            # Get current canvas dimensions. Canvas might not have its final size yet if window just opened.
            self.master.update_idletasks() # Process pending geometry changes to get correct canvas size.
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            img_width, img_height = self.image.size # Original image dimensions
            
            # Calculate top-left (image_x, image_y) to center the image at zoom_factor 1.0.
            # If image is smaller than canvas, center it.
            # If image is larger, position its top-left at canvas (0,0) or based on preferred policy.
            # Current policy: Center if smaller, else align top-left of image with canvas top-left.
            
            scaled_img_width = img_width * self.zoom_factor # at this point, zoom_factor is 1.0
            scaled_img_height = img_height * self.zoom_factor

            if scaled_img_width < canvas_width:
                self.image_x = (canvas_width - scaled_img_width) / 2
            else:
                self.image_x = 0 # Image is wider than canvas, align left

            if scaled_img_height < canvas_height:
                self.image_y = (canvas_height - scaled_img_height) / 2
            else:
                self.image_y = 0 # Image is taller than canvas, align top
            
            self.update_display()

        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {filepath}")
            self.image = None # Ensure image is None if opening failed
        except Exception as e:
            # Catch other potential Pillow errors (e.g., unrecognized format, truncated file)
            messagebox.showerror("Error Opening Image", f"Could not open or read image file:\n{filepath}\n\nDetails: {e}")
            self.image = None # Ensure image is None if opening failed

    def update_display(self):
        """
        Redraw the image on the canvas based on current zoom and position.

        This method resizes the original image according to `self.zoom_factor`,
        then creates a new PhotoImage and places it on the canvas at
        `(self.image_x, self.image_y)`.
        """
        if self.image is None:
            return # No image loaded, nothing to display.

        # Delete the old image from the canvas if it exists.
        if self.image_on_canvas:
            self.canvas.delete(self.image_on_canvas)

        # Calculate new dimensions, ensuring they are at least 1 pixel.
        new_width = max(1, int(self.image.width * self.zoom_factor))
        new_height = max(1, int(self.image.height * self.zoom_factor))

        try:
            # Resize the original image using Pillow's LANCZOS filter for quality.
            resized_image = self.image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            # Convert the Pillow image to a Tkinter PhotoImage.
            # This PhotoImage must be stored as an instance variable to prevent garbage collection.
            self.tk_image = ImageTk.PhotoImage(resized_image)
            
            # Create the image on the canvas at the current (image_x, image_y) position.
            self.image_on_canvas = self.canvas.create_image(
                self.image_x, self.image_y, anchor="nw", image=self.tk_image, tags="image_tag" # Added a tag
            )
            # self.canvas.config(scrollregion=self.canvas.bbox("image_tag")) # Optional: if using scrollbars
        except Exception as e:
            # Catch potential errors during resize or PhotoImage creation.
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
            return # No image loaded, cannot zoom.

        zoom_step = 0.1 # Proportional zoom step.
        
        # Store the zoom factor before it's modified by the current event.
        # This is crucial for correctly calculating the image point under the cursor.
        previous_zoom_factor = self.zoom_factor

        # Determine zoom direction based on event properties.
        if event.num == 4 or event.delta > 0:  # Scroll up (zoom in)
            self.zoom_factor *= (1 + zoom_step)
        elif event.num == 5 or event.delta < 0:  # Scroll down (zoom out)
            self.zoom_factor *= (1 - zoom_step)
        else:
            # This case should ideally not be reached with standard mouse wheels.
            return
        
        # Clamp the zoom factor to predefined min/max values.
        self.zoom_factor = max(0.1, min(self.zoom_factor, 5.0)) # Min 10%, Max 500% zoom.

        # --- Zoom towards cursor logic ---
        # Get mouse coordinates relative to the canvas.
        mouse_x = event.x
        mouse_y = event.y

        # Calculate the point on the *original, unzoomed* image that is currently under the mouse cursor.
        # 1. (mouse_x - self.image_x): x-coordinate of the mouse cursor relative to the top-left of the *currently displayed scaled* image.
        # 2. Divide by `previous_zoom_factor`: This converts the coordinate from the currently scaled image space back to the original image space.
        img_coord_x_on_original = (mouse_x - self.image_x) / previous_zoom_factor
        img_coord_y_on_original = (mouse_y - self.image_y) / previous_zoom_factor
        
        # Calculate the new top-left position (self.image_x, self.image_y) of the scaled image on the canvas.
        # The goal is to keep the `img_coord_on_original` point fixed under the mouse cursor after the new zoom.
        # The new on-canvas position of `img_coord_on_original` (after applying the new self.zoom_factor) would be:
        #    new_canvas_pos_of_img_point_x = self.image_x + (img_coord_x_on_original * self.zoom_factor)
        # We want this `new_canvas_pos_of_img_point_x` to be equal to the current `mouse_x`.
        # So, mouse_x = self.image_x + (img_coord_x_on_original * self.zoom_factor)
        # Rearranging for self.image_x:
        self.image_x = mouse_x - (img_coord_x_on_original * self.zoom_factor)
        self.image_y = mouse_y - (img_coord_y_on_original * self.zoom_factor)
        
        self.update_display() # Redraw the image with the new zoom and position.

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
            
            self.update_display() # Redraw the image at the new position.

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
        if self.image is None:
            messagebox.showinfo("No Image", "No image loaded to save.")
            return

        if not PIL_AVAILABLE:
            messagebox.showerror("Error", "Pillow library is not available. Cannot save images.")
            return

        # Get current dimensions of the canvas.
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # --- Calculate Crop Coordinates ---
        # 1. Determine the visible rectangle on the *scaled* image, in the scaled image's coordinate system.
        #    The canvas top-left is (0,0). The scaled image's top-left on canvas is (self.image_x, self.image_y).
        #    So, the point (0,0) on canvas corresponds to (-self.image_x, -self.image_y) on the scaled image.
        scaled_img_visible_x1 = -self.image_x
        scaled_img_visible_y1 = -self.image_y
        scaled_img_visible_x2 = -self.image_x + canvas_width
        scaled_img_visible_y2 = -self.image_y + canvas_height
        
        # 2. Convert these coordinates from the scaled image space to the *original* image space.
        #    This is done by dividing by the current zoom factor.
        original_img_crop_x1 = scaled_img_visible_x1 / self.zoom_factor
        original_img_crop_y1 = scaled_img_visible_y1 / self.zoom_factor
        original_img_crop_x2 = scaled_img_visible_x2 / self.zoom_factor
        original_img_crop_y2 = scaled_img_visible_y2 / self.zoom_factor

        # 3. Clamp these coordinates to the boundaries of the original image.
        #    This ensures that the crop box does not extend beyond the actual image dimensions.
        img_width, img_height = self.image.size
        final_crop_x1 = max(0, original_img_crop_x1)
        final_crop_y1 = max(0, original_img_crop_y1)
        final_crop_x2 = min(img_width, original_img_crop_x2)
        final_crop_y2 = min(img_height, original_img_crop_y2)

        # 4. Validate the final crop box.
        #    If the calculated width or height is zero or negative, it means no valid part
        #    of the image is visible (e.g., image panned completely off-screen).
        if final_crop_x1 >= final_crop_x2 or final_crop_y1 >= final_crop_y2:
            messagebox.showerror("Error", "No part of the image is visible to save, or the visible area is invalid.")
            return

        # 5. Ensure coordinates are integers for Pillow's crop method, as it expects a tuple of ints.
        crop_box = (
            int(round(final_crop_x1)), # Rounding can be better than truncating with int() for sub-pixel precision issues
            int(round(final_crop_y1)),
            int(round(final_crop_x2)),
            int(round(final_crop_y2))
        )

        # --- Prompt for Save Location and Save ---
        filepath = filedialog.asksaveasfilename(
            title="Save Cropped Image As...",
            defaultextension=".png",
            filetypes=[
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg;*.jpeg"),
                ("BMP files", "*.bmp"),
                ("GIF files", "*.gif"),
                ("All files", "*.*")
            ]
        )

        if not filepath:
            return

        try:
            cropped_image = self.image.crop(crop_box)
            cropped_image.save(filepath)
            messagebox.showinfo("Success", f"Cropped image saved successfully to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Error Saving Image", f"An error occurred while saving the image: {e}")


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
