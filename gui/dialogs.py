"""
Dialog windows for the Workflow Generator application.
Contains TemplateManager, LoadingScreen, and SettingsPanel classes.
"""

import tkinter as tk
import tkinter.scrolledtext as scrolledtext
from tkinter import ttk, messagebox
import os
import json
import random
from typing import Optional
from dataclasses import asdict
from PIL import Image, ImageTk

from gui.editors import TemplateEditor


class TemplateManager(tk.Toplevel):
    """GUI for managing user-created workflow templates."""
    def __init__(self, parent, app: 'WorkflowApp'):
        super().__init__(parent)
        self.app = app
        
        self.title("Template Manager")
        self.geometry("500x400")
        self.grab_set()
        self.transient(parent)

        colors = self.app.themes[self.app.current_theme]
        self.config(bg=colors["bg"])

        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(top_frame, text="Manage your custom templates.").pack(side=tk.LEFT)

        list_frame = ttk.Frame(self)
        list_frame.pack(expand=True, fill=tk.BOTH, padx=10)
        
        self.listbox = tk.Listbox(list_frame, bg=colors["widget_bg"], fg=colors["widget_fg"])
        self.listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Create", command=self.create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Edit", command=self.edit_selected).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Delete", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        self.load_template_list()

    def load_template_list(self):
        self.listbox.delete(0, tk.END)
        try:
            for filename in sorted(os.listdir(self.app.templates_dir)):
                if filename.endswith(".json"):
                    self.listbox.insert(tk.END, filename)
        except Exception as e:
            self.app.show_error("Template Load Error", f"Failed to load template list: {e}")

    def create_new(self):
        editor = TemplateEditor(self, self.app)
        self.wait_window(editor)
        self.load_template_list()

    def edit_selected(self):
        selected = self.listbox.curselection()
        if not selected:
            self.app.show_warning("No Selection", "Please select a template to edit.")
            return
        template_name = self.listbox.get(selected[0])
        editor = TemplateEditor(self, self.app, template_name)
        self.wait_window(editor)
        self.load_template_list()

    def delete_selected(self):
        selected = self.listbox.curselection()
        if not selected:
            self.app.show_warning("No Selection", "Please select a template to delete.")
            return
        template_name = self.listbox.get(selected[0])
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{template_name}'?", parent=self):
            try:
                os.remove(os.path.join(self.app.templates_dir, template_name))
                self.load_template_list()
                self.app.load_templates()
            except Exception as e:
                self.app.show_error("Delete Error", f"Failed to delete template: {e}")


class LoadingScreen:
    """A hacker-themed loading screen that appears before the main UI."""
    def __init__(self, parent):
        self.root = tk.Toplevel(parent)
        self.root.title("Loading")
        self.root.geometry("800x600")
        self.root.configure(bg='#000000')
        self.root.overrideredirect(True)  # Frameless window

        # Center the window
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 800) // 2
        y = (screen_height - 600) // 2
        self.root.geometry(f"800x600+{x}+{y}")

        self.canvas = tk.Canvas(self.root, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Load and display the image
        try:
            # Get the directory where this file is located
            current_dir = os.path.dirname(os.path.abspath(__file__))
            assets_dir = os.path.join(current_dir, "..", "assets")
            image_path = os.path.join(assets_dir, "1.png")
            
            # Load and resize the image to fit nicely on screen
            image = Image.open(image_path)
            # Resize to about 30% of the canvas size
            resized_image = image.resize((240, 180), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(resized_image)
            
            # Place the image slightly above the vertical center
            self.image_id = self.canvas.create_image(400, 250, image=self.photo)
        except Exception as e:
            print(f"Could not load image: {e}")
            self.image_id = None

        # Create the text below the image
        self.text_id = self.canvas.create_text(
            400, 350, text="Created by Vedant K",
            font=("Courier", 20, "bold"), fill="#00ff00"
        )
        
        # Ensure image is behind text if both are present
        if self.image_id:
            self.canvas.tag_lower(self.image_id, self.text_id)

        self.glow_color_index = 0
        self.glow_colors = ["#00ff00", "#33ff33", "#66ff66", "#99ff99", "#66ff66", "#33ff33"]

        self.font_size = 12
        self.streams = []
        self.setup_matrix()

        self.root.attributes('-alpha', 0.0)
        self.fade_in()
        self.animate_glow()
        self.animate_matrix()

        self.root.after(5000, self.fade_out)

    def get_random_char(self):
        return chr(random.randint(33, 126))

    def setup_matrix(self):
        font_width = self.font_size // 1.5 # Approximate width
        for x in range(0, 800, int(font_width)):
            y = random.randint(-600, 0)
            speed = random.randint(2, 6)
            stream_length = random.randint(10, 30)
            stream = []
            for i in range(stream_length):
                char = self.get_random_char()
                text_id = self.canvas.create_text(x, y - i * self.font_size, text=char, font=("Courier", self.font_size), fill="#00ff00")
                stream.append(text_id)
            self.streams.append({"stream": stream, "y": y, "speed": speed, "len": stream_length})

    def animate_matrix(self):
        for s in self.streams:
            s["y"] += s["speed"]
            if s["y"] - s["len"] * self.font_size > 600:
                s["y"] = random.randint(-600, 0)
                s["speed"] = random.randint(2, 6)

            for i, text_id in enumerate(s["stream"]):
                self.canvas.coords(text_id, self.canvas.coords(text_id)[0], s["y"] - i * self.font_size)
                if i == s["len"] - 1: # Head of the stream
                    self.canvas.itemconfig(text_id, fill="#ccffcc")
                elif i > s["len"] - 5: # Near the head
                    self.canvas.itemconfig(text_id, fill="#66ff66")
                else:
                    self.canvas.itemconfig(text_id, fill="#009900")
                
                if random.random() < 0.1: # 10% chance to change character
                    self.canvas.itemconfig(text_id, text=self.get_random_char())

        # Keep main text and image on top of matrix
        if self.image_id:
            self.canvas.tag_raise(self.image_id)
        self.canvas.tag_raise(self.text_id)
        self.root.after(30, self.animate_matrix)

    def animate_glow(self):
        color = self.glow_colors[self.glow_color_index]
        self.canvas.itemconfig(self.text_id, fill=color)
        self.glow_color_index = (self.glow_color_index + 1) % len(self.glow_colors)
        self.root.after(200, self.animate_glow)

    def fade_in(self):
        alpha = self.root.attributes("-alpha")
        if alpha < 1.0:
            alpha += 0.05
            self.root.attributes("-alpha", alpha)
            self.root.after(20, self.fade_in)

    def fade_out(self):
        alpha = self.root.attributes("-alpha")
        if alpha > 0.0:
            alpha -= 0.05
            self.root.attributes("-alpha", alpha)
            self.root.after(20, self.fade_out)
        else:
            self.root.destroy()


class SettingsPanel(tk.Toplevel):
    """GUI for managing application settings."""
    def __init__(self, parent, app: 'WorkflowApp'):
        super().__init__(parent)
        self.app = app
        
        self.title("Settings")
        self.geometry("400x300")
        self.grab_set()
        self.transient(parent)

        colors = self.app.themes[self.app.current_theme]
        self.config(bg=colors["bg"])

        # Create a main frame to hold the notebook with scrollbars
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create a canvas and scrollbar for the notebook
        canvas = tk.Canvas(main_frame, bg=colors["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        # Configure scrolling
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel to canvas for scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        scrollable_frame.bind("<MouseWheel>", _on_mousewheel)
        
        # Create notebook inside scrollable frame
        notebook = ttk.Notebook(scrollable_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="General")

        # Autosave settings
        autosave_frame = ttk.LabelFrame(general_frame, text="Autosave")
        autosave_frame.pack(fill=tk.X, padx=10, pady=10)

        self.autosave_var = tk.BooleanVar(value=self.app.autosave_enabled)
        autosave_check = ttk.Checkbutton(autosave_frame, text="Enable Autosave", variable=self.autosave_var)
        autosave_check.pack(anchor=tk.W, padx=5, pady=2)

        ttk.Label(autosave_frame, text="Autosave Interval (seconds):").pack(anchor=tk.W, padx=5, pady=2)
        self.autosave_interval_var = tk.IntVar(value=self.app.autosave_interval // 1000)
        ttk.Entry(autosave_frame, textvariable=self.autosave_interval_var, width=10).pack(anchor=tk.W, padx=5, pady=2)

        # Theme settings
        theme_frame = ttk.LabelFrame(general_frame, text="Theme")
        theme_frame.pack(fill=tk.X, padx=10, pady=10)

        self.theme_var = tk.StringVar(value=self.app.current_theme)
        for theme_name in self.app.themes:
            ttk.Radiobutton(theme_frame, text=theme_name.title(), value=theme_name, variable=self.theme_var).pack(anchor=tk.W, padx=5)
        
        # Animation settings
        animation_frame = ttk.LabelFrame(general_frame, text="Animation")
        animation_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.animation_var = tk.BooleanVar(value=self.app.animation_enabled)
        animation_check = ttk.Checkbutton(animation_frame, text="Enable Neural Network Animation", variable=self.animation_var)
        animation_check.pack(anchor=tk.W, padx=5, pady=2)
        
        ttk.Label(animation_frame, text="Animation Speed:").pack(anchor=tk.W, padx=5, pady=(10, 2))
        self.animation_speed_var = tk.DoubleVar(value=getattr(self.app, 'animation_speed', 1.0))
        speed_scale = ttk.Scale(animation_frame, from_=0.1, to=3.0, variable=self.animation_speed_var, orient=tk.HORIZONTAL)
        speed_scale.pack(fill=tk.X, padx=5, pady=2)
        speed_label = ttk.Label(animation_frame, text="1.0x")
        speed_label.pack(anchor=tk.W, padx=5)
        
        # Update speed label when slider moves
        def update_speed_label(val):
            speed_label.config(text=f"{float(val):.1f}x")
        speed_scale.config(command=update_speed_label)
        
        # Adaptive Interface settings
        adaptive_frame = ttk.LabelFrame(general_frame, text="Adaptive Interface")
        adaptive_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.adaptive_var = tk.BooleanVar(value=self.app.adaptive_interface_enabled)
        adaptive_check = ttk.Checkbutton(adaptive_frame, text="Enable Adaptive Neural Interface", variable=self.adaptive_var)
        adaptive_check.pack(anchor=tk.W, padx=5, pady=2)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(button_frame, text="Save", command=self.save_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

    def save_settings(self):
        self.app.autosave_enabled = self.autosave_var.get()
        self.app.autosave_interval = self.autosave_interval_var.get() * 1000
        self.app.animation_enabled = self.animation_var.get()
        self.app.animation_speed = self.animation_speed_var.get()
        self.app.adaptive_interface_enabled = self.adaptive_var.get()
        self.app.set_theme(self.theme_var.get())
        self.app.save_settings()
        self.destroy()