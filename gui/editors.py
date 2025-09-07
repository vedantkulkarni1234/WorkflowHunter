"""
Editor windows for the Workflow Generator application.
Contains WorkflowEditor and TemplateEditor classes.
"""

import tkinter as tk
import tkinter.scrolledtext as scrolledtext
from tkinter import ttk
import json
import os
from typing import Optional

from models import WorkflowStep, Workflow


class WorkflowEditor(tk.Toplevel):
    """GUI for editing workflow steps"""
    
    def __init__(self, parent, step: Optional[WorkflowStep] = None, workflow: Optional[Workflow] = None):
        super().__init__(parent)
        self.app = parent.app
        self.step = step or WorkflowStep()
        self.workflow = workflow
        self.title("Edit Workflow Step")
        self.geometry("600x550")
        self.grab_set()
        self.transient(parent)
        
        colors = self.app.themes[self.app.current_theme]
        self.config(bg=colors["bg"])
        
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        basic_frame = ttk.Frame(notebook)
        notebook.add(basic_frame, text="Basic")
        
        ttk.Label(basic_frame, text="Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.name_var = tk.StringVar(value=self.step.name)
        ttk.Entry(basic_frame, textvariable=self.name_var, width=50).grid(row=0, column=1, sticky=tk.W+tk.E, pady=2)

        ttk.Label(basic_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.desc_var = tk.StringVar(value=self.step.description)
        ttk.Entry(basic_frame, textvariable=self.desc_var, width=50).grid(row=1, column=1, sticky=tk.W+tk.E, pady=2)

        ttk.Label(basic_frame, text="Command:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.command_text = tk.Text(basic_frame, height=5)
        self.command_text.grid(row=2, column=1, sticky=tk.W+tk.E, pady=2)
        self.command_text.insert("1.0", self.step.command)

        basic_frame.columnconfigure(1, weight=1)
        
        adv_frame = ttk.Frame(notebook)
        notebook.add(adv_frame, text="Advanced")
        
        # Conditional logic section
        cond_frame = ttk.LabelFrame(adv_frame, text="Conditional Execution")
        cond_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(cond_frame, text="Condition Type:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.condition_type_var = tk.StringVar(value=self.step.condition_type)
        condition_type_combo = ttk.Combobox(cond_frame, textvariable=self.condition_type_var, 
                                           values=["none", "if", "unless"], state="readonly", width=15)
        condition_type_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(cond_frame, text="Condition Expression:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.condition_expr_text = tk.Text(cond_frame, height=3)
        self.condition_expr_text.grid(row=1, column=1, sticky=tk.W+tk.E, pady=2)
        self.condition_expr_text.insert("1.0", self.step.condition_expression)
        
        # Help text for condition expressions
        help_text = "Use expressions like:\n{previous_step.exit_code} == 0\n{previous_step.findings_count} > 5\n{step_name.exit_code} != 0"
        ttk.Label(cond_frame, text=help_text, foreground="gray").grid(row=2, column=1, sticky=tk.W, pady=2)
        
        cond_frame.columnconfigure(1, weight=1)

        notes_frame = ttk.Frame(notebook)
        notebook.add(notes_frame, text="Notes")

        ttk.Label(notes_frame, text="Step Notes:").pack(anchor=tk.W, padx=5, pady=5)
        self.notes_text = tk.Text(notes_frame, height=10, relief=tk.FLAT)
        self.notes_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.notes_text.insert("1.0", self.step.notes)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(button_frame, text="Save", command=self.save_step).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

    def save_step(self):
        self.step.name = self.name_var.get()
        self.step.description = self.desc_var.get()
        self.step.command = self.command_text.get("1.0", tk.END).strip()
        self.step.condition_type = self.condition_type_var.get()
        self.step.condition_expression = self.condition_expr_text.get("1.0", tk.END).strip()
        self.step.notes = self.notes_text.get("1.0", tk.END).strip()
        self.app.update_workflow_display()
        self.destroy()


class TemplateEditor(tk.Toplevel):
    """Editor for creating and modifying workflow templates from JSON."""
    def __init__(self, parent, app: 'WorkflowApp', template_name: Optional[str] = None):
        super().__init__(parent)
        self.app = app
        self.template_name = template_name
        
        self.title(f"Edit Template: {template_name}" if template_name else "Create New Template")
        self.geometry("800x600")
        self.grab_set()
        self.transient(parent)

        colors = self.app.themes[self.app.current_theme]
        self.config(bg=colors["bg"])

        self.text_widget = scrolledtext.ScrolledText(self, wrap=tk.WORD, undo=True)
        self.text_widget.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        self.text_widget.config(bg=colors["widget_bg"], fg=colors["widget_fg"], insertbackground=colors["fg"])

        if template_name:
            try:
                filepath = os.path.join(self.app.templates_dir, template_name)
                with open(filepath, 'r') as f:
                    content = f.read()
                self.text_widget.insert('1.0', content)
            except Exception as e:
                self.app.show_error("Template Load Error", f"Failed to load template: {e}")
                self.destroy()

        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(button_frame, text="Save", command=self.save_template).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

    def save_template(self):
        content = self.text_widget.get("1.0", tk.END)
        try:
            data = json.loads(content)
            if "name" not in data or not isinstance(data.get("steps"), list):
                raise ValueError("Template must have a 'name' and a 'steps' list.")

            filename = data["name"].lower().replace(" ", "_").replace("/", "") + ".json"
            
            if self.template_name and self.template_name != filename:
                os.remove(os.path.join(self.app.templates_dir, self.template_name))

            save_path = os.path.join(self.app.templates_dir, filename)
            with open(save_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.app.show_info("Success", "Template saved successfully.")
            self.app.load_templates()
            self.destroy()
            
        except json.JSONDecodeError:
            self.app.show_error("Invalid JSON", "Invalid JSON format.")
        except Exception as e:
            self.app.show_error("Save Error", f"Failed to save template: {e}")