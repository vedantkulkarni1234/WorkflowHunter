"""
Main application window for the Workflow Generator.
Contains the WorkflowApp class which orchestrates the entire GUI.
"""

import tkinter as tk
import tkinter.scrolledtext as scrolledtext
from tkinter import ttk, messagebox, filedialog
import json
import yaml
import uuid
import threading
import copy
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from models import Workflow, WorkflowStep, ExecutionResult, StepStatus, UserInteraction
from workflow_engine import WorkflowRunner, VariableResolver
from gui.canvas import WorkflowCanvas
from gui.editors import WorkflowEditor, TemplateEditor
from gui.dialogs import TemplateManager, LoadingScreen, SettingsPanel

logger = logging.getLogger(__name__)


class WorkflowApp:
    """Main application window"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw() # Hide the main window initially
        self.loading_screen = LoadingScreen(self.root)
        self.root.app = self
        self.root.title("Bug Bounty Workflow Generator")
        self.root.geometry("1200x800")
        
        self.current_workflow = Workflow()
        self.runner = WorkflowRunner()
        self.selected_step_id: Optional[str] = None
        self.current_filepath: Optional[str] = None
        self.autosave_enabled = True
        self.animation_enabled = True  # Neural network animation feature
        self.animation_speed = 1.0  # Default animation speed
        
        # Adaptive Neural Interface features
        self.user_interactions: List[UserInteraction] = []  # Track user interactions
        self.user_preferences = {}  # Store learned user preferences
        self.adaptive_interface_enabled = True  # Enable adaptive interface
        
        self.templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir)
            self.create_default_template()

        self.themes = {
            "light": {
                "bg": "#F0F0F0", "fg": "black", "widget_bg": "white", "widget_fg": "black",
                "canvas_bg": "white", "node_pending": "lightblue", "node_running": "yellow",
                "node_success": "lightgreen", "node_failed": "salmon", "node_skipped": "lightgrey",
                "node_timeout": "orange", "node_outline": "blue", "node_text": "black", "conn_color": "blue",
            },
            "dark": {
                "bg": "#2E2E2E", "fg": "#FFFFFF", "widget_bg": "#3C3C3C", "widget_fg": "#FFFFFF",
                "canvas_bg": "#2E2E2E", "node_pending": "#3A4A6A", "node_running": "#A8A838",
                "node_success": "#3D6B4D", "node_failed": "#7B4B4B", "node_skipped": "#555555",
                "node_timeout": "#A96013", "node_outline": "#6A8EC3", "node_text": "white", "conn_color": "#6A8EC3",
            }
        }
        self.current_theme = "light"
        self.style = ttk.Style(self.root)
        
        self.load_settings()

        self.autosave_interval = 60000  # 60 seconds in milliseconds
        self.last_saved_label = ttk.Label(self.root, text="", anchor=tk.W)
        self.last_saved_label.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
        self.autosave_id = None

        self.create_ui()
        self.load_templates()
        self.set_theme("light")
        self.update_workflow_display()
        self.schedule_autosave()
    
    def show_error(self, title: str, message: str):
        """Standardized error reporting to the GUI"""
        logger.error(f"{title}: {message}")
        messagebox.showerror(title, message, parent=self.root)
        
    def show_warning(self, title: str, message: str):
        """Standardized warning reporting to the GUI"""
        logger.warning(f"{title}: {message}")
        messagebox.showwarning(title, message, parent=self.root)
        
    def show_info(self, title: str, message: str):
        """Standardized info reporting to the GUI"""
        logger.info(f"{title}: {message}")
        messagebox.showinfo(title, message, parent=self.root)

    def load_settings(self):
        try:
            with open("settings.json", 'r') as f:
                settings = json.load(f)
                self.current_theme = settings.get("theme", "light")
                self.autosave_enabled = settings.get("autosave_enabled", True)
                self.autosave_interval = settings.get("autosave_interval", 60000)
                self.animation_enabled = settings.get("animation_enabled", True)
                self.animation_speed = settings.get("animation_speed", 1.0)
                self.adaptive_interface_enabled = settings.get("adaptive_interface_enabled", True)
                self.user_preferences = settings.get("user_preferences", {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.current_theme = "light"
            self.autosave_enabled = True
            self.autosave_interval = 60000
            self.show_warning("Settings Load Error", f"Could not load settings, using defaults: {e}")
        
        # Load user interaction data
        self._load_user_data()
    
    def _load_user_data(self):
        """Load user interaction data from disk"""
        try:
            if os.path.exists("user_data.json"):
                with open("user_data.json", 'r') as f:
                    user_data = json.load(f)
                    # Convert interaction data back to UserInteraction objects
                    interaction_data = user_data.get("interactions", [])
                    self.user_interactions = [UserInteraction(**data) for data in interaction_data]
                    self.user_preferences = user_data.get("preferences", {})
        except Exception as e:
            logger.error(f"Failed to load user data: {e}")

    def save_settings(self):
        settings = {
            "theme": self.current_theme,
            "autosave_enabled": self.autosave_enabled,
            "autosave_interval": self.autosave_interval,
            "animation_enabled": self.animation_enabled,
            "animation_speed": self.animation_speed,
            "adaptive_interface_enabled": self.adaptive_interface_enabled,
            "user_preferences": self.user_preferences
        }
        try:
            with open("settings.json", 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            self.show_error("Settings Save Error", f"Failed to save settings: {e}")
    
    def track_user_interaction(self, action: str, target: str, context: str = "general", duration: float = 0.0):
        """Track a user interaction for adaptive interface learning"""
        if not self.adaptive_interface_enabled:
            return
            
        interaction = UserInteraction(
            timestamp=datetime.now().isoformat(),
            action=action,
            target=target,
            context=context,
            duration=duration
        )
        self.user_interactions.append(interaction)
        
        # Update user preferences based on interactions
        self._update_user_preferences(interaction)
        
        # Adapt interface based on context changes
        self._adapt_interface_to_context()
        
        # Save interactions periodically
        if len(self.user_interactions) % 10 == 0:
            self._save_user_data()
    
    def _adapt_interface_to_context(self):
        """Adapt the interface based on the current context"""
        if not self.adaptive_interface_enabled:
            return
            
        # Determine current context
        current_context = self._determine_current_context()
        
        # Re-apply theme to adapt colors
        self.set_theme(self.current_theme)
        
        # Rearrange UI elements based on usage patterns
        self._rearrange_ui_elements(current_context)
        
        # Create guidance particles for anticipatory guidance
        if self.canvas:
            self.canvas.create_guidance_particles(current_context)
        
        # Update recommendations panel
        self._update_recommendations_panel(current_context)
    
    def _update_recommendations_panel(self, context: str = "general"):
        """Update the recommendations panel with personalized suggestions"""
        if not self.adaptive_interface_enabled:
            return
            
        # Clear existing content
        for widget in self.recommendations_frame.winfo_children():
            widget.destroy()
        
        # Get recommendations
        recommendations = self.get_user_recommendations(context)
        
        # Create UI elements for recommendations
        if recommendations["steps"] or recommendations["templates"]:
            # Create a frame for steps
            if recommendations["steps"]:
                steps_label = ttk.Label(self.recommendations_frame, text="Suggested Steps:", font=("TkDefaultFont", 9, "bold"))
                steps_label.pack(anchor=tk.W, padx=5, pady=(5, 0))
                
                for step_name, count in recommendations["steps"][:3]:  # Top 3
                    step_btn = ttk.Button(
                        self.recommendations_frame, 
                        text=f"{step_name} ({count} uses)",
                        command=lambda name=step_name: self._add_recommended_step(name),
                        width=30
                    )
                    step_btn.pack(fill=tk.X, padx=5, pady=2)
            
            # Create a frame for templates
            if recommendations["templates"]:
                templates_label = ttk.Label(self.recommendations_frame, text="Suggested Templates:", font=("TkDefaultFont", 9, "bold"))
                templates_label.pack(anchor=tk.W, padx=5, pady=(10, 0))
                
                for template_name, count in recommendations["templates"][:2]:  # Top 2
                    # Strip .json extension for display
                    display_name = template_name.replace(".json", "") if template_name.endswith(".json") else template_name
                    template_btn = ttk.Button(
                        self.recommendations_frame, 
                        text=f"{display_name} ({count} uses)",
                        command=lambda name=template_name: self._load_recommended_template(name),
                        width=30
                    )
                    template_btn.pack(fill=tk.X, padx=5, pady=2)
        else:
            # Show a message when there are no recommendations yet
            no_rec_label = ttk.Label(
                self.recommendations_frame, 
                text="Use the application to get personalized recommendations",
                foreground="gray"
            )
            no_rec_label.pack(padx=5, pady=20)
    
    def _add_recommended_step(self, step_name: str):
        """Add a recommended step to the current workflow"""
        # Track this interaction
        self.track_user_interaction("ui_element_used", "recommended_step", "general")
        
        # Create a new step with the recommended name
        new_step = WorkflowStep(name=step_name)
        editor = WorkflowEditor(self.root, new_step, self.current_workflow)
        self.root.wait_window(editor)
        
        if new_step.name:
            self.current_workflow.steps.append(new_step)
            self.update_workflow_display()
            # Track this interaction
            self.track_user_interaction("step_added", new_step.name)
    
    def _load_recommended_template(self, template_name: str):
        """Load a recommended template"""
        # Track this interaction
        self.track_user_interaction("ui_element_used", "recommended_template", "general")
        
        # Find and load the template
        template = self.templates.get(template_name.replace(".json", "") if template_name.endswith(".json") else template_name)
        if template:
            self.load_template(template)
            # Track this interaction
            self.track_user_interaction("template_used", template.name)
        else:
            self.show_warning("Template Not Found", f"Could not find template: {template_name}")
    
    def _rearrange_ui_elements(self, context: str):
        """Rearrange UI elements based on usage patterns for the given context"""
        if not self.adaptive_interface_enabled or context not in self.user_preferences:
            return
            
        context_prefs = self.user_preferences[context]
        
        # Get frequently used templates and steps
        frequent_templates = context_prefs.get("frequently_used_templates", {})
        frequent_steps = context_prefs.get("frequently_used_steps", {})
        
        # Sort by frequency of use
        sorted_templates = sorted(frequent_templates.items(), key=lambda x: x[1], reverse=True)
        sorted_steps = sorted(frequent_steps.items(), key=lambda x: x[1], reverse=True)
        
        # For now, we'll just log this information
        # In a more advanced implementation, we could dynamically modify the UI
        if sorted_templates or sorted_steps:
            logger.info(f"Adaptive UI for {context}:")
            if sorted_templates:
                logger.info(f"  Top templates: {sorted_templates[:3]}")
            if sorted_steps:
                logger.info(f"  Top steps: {sorted_steps[:5]}")
    
    def _update_user_preferences(self, interaction: UserInteraction):
        """Update user preferences based on interactions"""
        # Initialize preference tracking if needed
        if interaction.context not in self.user_preferences:
            self.user_preferences[interaction.context] = {
                "frequently_used_steps": {},
                "frequently_used_templates": {},
                "preferred_tools": {},
                "ui_layout_preferences": {}
            }
        
        context_prefs = self.user_preferences[interaction.context]
        
        # Track frequently used steps
        if interaction.action == "step_added" or interaction.action == "step_executed":
            step_name = interaction.target
            context_prefs["frequently_used_steps"][step_name] = context_prefs["frequently_used_steps"].get(step_name, 0) + 1
        
        # Track frequently used templates
        if interaction.action == "template_used":
            template_name = interaction.target
            context_prefs["frequently_used_templates"][template_name] = context_prefs["frequently_used_templates"].get(template_name, 0) + 1
            
        # Track UI element usage
        if interaction.action == "ui_element_used":
            element_name = interaction.target
            context_prefs["ui_layout_preferences"][element_name] = context_prefs["ui_layout_preferences"].get(element_name, 0) + 1
            
        # Determine context from step names or commands
        self._infer_context_from_interaction(interaction)
        
        # Update predictive model
        self._update_predictive_model()
    
    def _update_predictive_model(self):
        """Simple predictive model based on frequency analysis"""
        # This is a basic implementation that could be enhanced with more sophisticated ML
        # For now, we'll just use frequency-based recommendations
        
        # Combine data from all contexts for overall preferences
        overall_steps = {}
        overall_templates = {}
        
        for context, prefs in self.user_preferences.items():
            for step, count in prefs.get("frequently_used_steps", {}).items():
                overall_steps[step] = overall_steps.get(step, 0) + count
                
            for template, count in prefs.get("frequently_used_templates", {}).items():
                overall_templates[template] = overall_templates.get(template, 0) + count
        
        # Store top recommendations
        self.user_preferences["recommendations"] = {
            "steps": sorted(overall_steps.items(), key=lambda x: x[1], reverse=True)[:10],
            "templates": sorted(overall_templates.items(), key=lambda x: x[1], reverse=True)[:5]
        }
    
    def _infer_context_from_interaction(self, interaction: UserInteraction):
        """Infer the context (recon, exploit, report) from interaction details"""
        target = interaction.target.lower()
        action = interaction.action.lower()
        
        # Determine context based on keywords
        if any(keyword in target for keyword in ["subfinder", "amass", "dns", "scan", "enum", "recon"]):
            interaction.context = "reconnaissance"
        elif any(keyword in target for keyword in ["exploit", "payload", "attack", "vuln", "nmap"]):
            interaction.context = "exploitation"
        elif any(keyword in target for keyword in ["report", "export", "document", "summary"]):
            interaction.context = "reporting"
    
    def get_user_recommendations(self, context: str = "general") -> Dict[str, List]:
        """Get recommendations for the user based on their interaction history"""
        if not self.adaptive_interface_enabled:
            return {"steps": [], "templates": []}
            
        # Get context-specific recommendations
        if context in self.user_preferences:
            context_prefs = self.user_preferences[context]
            steps = list(context_prefs.get("frequently_used_steps", {}).items())
            templates = list(context_prefs.get("frequently_used_templates", {}).items())
            
            # Sort by frequency
            steps.sort(key=lambda x: x[1], reverse=True)
            templates.sort(key=lambda x: x[1], reverse=True)
            
            return {
                "steps": steps[:5],  # Top 5 steps
                "templates": templates[:3]  # Top 3 templates
            }
        
        # Fallback to general recommendations
        return self.user_preferences.get("recommendations", {"steps": [], "templates": []})
    
    def _save_user_data(self):
        """Save user interaction data to disk"""
        try:
            user_data = {
                "interactions": [asdict(interaction) for interaction in self.user_interactions],
                "preferences": self.user_preferences
            }
            with open("user_data.json", 'w') as f:
                json.dump(user_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save user data: {e}")

    def create_default_template(self):
        recon_workflow = Workflow(
            name="Subdomain Reconnaissance",
            description="Comprehensive subdomain discovery and enumeration",
            tags=["reconnaissance", "subdomain", "discovery"]
        )
        steps = [
            WorkflowStep(name="Subfinder", command="subfinder -d {target} -o {output_dir}/subfinder.txt", pos_x=50, pos_y=50),
            WorkflowStep(name="Amass", command="amass enum -d {target} -o {output_dir}/amass.txt", pos_x=50, pos_y=150),
            WorkflowStep(name="Combine", command="cat {output_dir}/*.txt | sort -u > {output_dir}/all.txt", pos_x=300, pos_y=100),
            WorkflowStep(name="Httpx", command="httpx -l {output_dir}/all.txt -o {output_dir}/alive.txt", pos_x=550, pos_y=100)
        ]
        steps[2].dependencies = [steps[0].id, steps[1].id]
        steps[3].dependencies = [steps[2].id]
        recon_workflow.steps = steps
        
        filepath = os.path.join(self.templates_dir, "subdomain_recon.json")
        try:
            with open(filepath, 'w') as f:
                json.dump(recon_workflow.to_dict(), f, indent=2)
        except Exception as e:
            self.show_error("Template Creation Error", f"Failed to create default template: {e}")

    def create_ui(self):
        """Create the main UI"""
        self.create_menu_bar()
        # ... rest of UI setup ...
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=2)
        
        info_frame = ttk.LabelFrame(left_frame, text="Workflow Information")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(info_frame, text="Name:").grid(row=0, column=0, sticky=tk.W)
        self.workflow_name_var = tk.StringVar()
        self.workflow_name_var.trace('w', self.on_workflow_name_changed)
        ttk.Entry(info_frame, textvariable=self.workflow_name_var, width=40).grid(row=0, column=1, sticky=tk.W+tk.E, padx=5)
        
        ttk.Label(info_frame, text="Description:").grid(row=1, column=0, sticky=tk.W)
        self.workflow_desc_var = tk.StringVar()
        self.workflow_desc_var.trace('w', self.on_workflow_desc_changed)
        ttk.Entry(info_frame, textvariable=self.workflow_desc_var, width=40).grid(row=1, column=1, sticky=tk.W+tk.E, padx=5)

        global_vars_frame = ttk.LabelFrame(left_frame, text="Global Variables")
        global_vars_frame.pack(fill=tk.X, padx=5, pady=5)

        self.global_vars_text = tk.Text(global_vars_frame, height=4, relief=tk.FLAT)
        self.global_vars_text.pack(fill=tk.X, padx=5, pady=2)
        self.global_vars_text.bind("<<Modified>>", self.on_global_vars_changed)

        info_frame.columnconfigure(1, weight=1)
        
        steps_frame = ttk.LabelFrame(left_frame, text="Workflow Canvas")
        steps_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        steps_toolbar = ttk.Frame(steps_frame)
        steps_toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(steps_toolbar, text="Add Step", command=self.add_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_toolbar, text="Edit Step", command=self.edit_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_toolbar, text="Delete Step", command=self.delete_step).pack(side=tk.LEFT, padx=2)

        ttk.Button(steps_toolbar, text="Reset Zoom", command=lambda: self.canvas.reset_zoom()).pack(side=tk.RIGHT, padx=2)
        ttk.Button(steps_toolbar, text="-", command=lambda: self.canvas.zoom_out()).pack(side=tk.RIGHT, padx=2)
        ttk.Button(steps_toolbar, text="+", command=lambda: self.canvas.zoom_in()).pack(side=tk.RIGHT, padx=2)
        
        canvas_frame = ttk.Frame(steps_frame)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = WorkflowCanvas(canvas_frame, self)
        
        self.v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.canvas.config(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        hint_label = ttk.Label(steps_frame, text="Hold Shift and drag between nodes to create a connection.")
        hint_label.pack(side=tk.BOTTOM, fill=tk.X, padx=5)
        
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)
        
        # Recommendations panel (adaptive interface)
        self.recommendations_frame = ttk.LabelFrame(right_frame, text="Recommendations")
        self.recommendations_frame.pack(fill=tk.X, padx=5, pady=5)
        self._update_recommendations_panel()
        
        exec_frame = ttk.LabelFrame(right_frame, text="Execution")
        exec_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(exec_frame, text="Variables:").pack(anchor=tk.W)
        self.variables_text = tk.Text(exec_frame, height=6, relief=tk.FLAT)
        self.variables_text.pack(fill=tk.X, padx=5, pady=2)
        self.variables_text.insert("1.0", "target=example.com\noutput_dir=/tmp/output")
        
        exec_buttons = ttk.Frame(exec_frame)
        exec_buttons.pack(fill=tk.X, pady=5)
        
        ttk.Button(exec_buttons, text="Dry Run", command=self.dry_run_workflow).pack(side=tk.LEFT, padx=2)
        ttk.Button(exec_buttons, text="Execute", command=self.execute_workflow).pack(side=tk.LEFT, padx=2)
        ttk.Button(exec_buttons, text="Abort", command=self.abort_execution).pack(side=tk.LEFT, padx=2)
        ttk.Button(exec_buttons, text="Restart", command=self.restart_application).pack(side=tk.RIGHT, padx=2)
        
        log_frame = ttk.LabelFrame(right_frame, text="Execution Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state=tk.DISABLED, relief=tk.FLAT)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def schedule_autosave(self):
        if self.autosave_id:
            self.root.after_cancel(self.autosave_id)
        if self.autosave_enabled:
            self.autosave_id = self.root.after(self.autosave_interval, self.autosave_workflow)

    def autosave_workflow(self):
        if self.current_filepath:
            try:
                data = self.current_workflow.to_dict()
                with open(self.current_filepath, 'w') as f:
                    if self.current_filepath.endswith(('.yaml', '.yml')):
                        yaml.dump(data, f, default_flow_style=False)
                    else:
                        json.dump(data, f, indent=2)
                self.last_saved_label.config(text=f"Last saved: {datetime.now().strftime('%H:%M:%S')}")
            except Exception as e:
                logger.error(f"Autosave failed: {e}")
                # We don't show an error dialog for autosave failures to avoid interrupting the user
        self.schedule_autosave() # Reschedule the next autosave
    
    def on_step_animation_update(self, step_id: str, event: str, status: Optional[StepStatus] = None):
        """Callback to handle animation updates during workflow execution"""
        if not self.animation_enabled:
            return
            
        # Start animation when step begins
        if event == "start":
            # Find all connections leading to this step
            step = next((s for s in self.current_workflow.steps if s.id == step_id), None)
            if step and self.canvas:
                # Track this interaction
                self.track_user_interaction("step_executed", step.name)
                
                # Create particles for each dependency connection
                for dep_id in step.dependencies:
                    # Find the connection line
                    for conn_id in self.canvas.connections:
                        tags = self.canvas.gettags(conn_id)
                        if f"conn-from-{dep_id}" in tags and f"conn-to-{step_id}" in tags:
                            # Determine activity type based on step command
                            dep_step = next((s for s in self.current_workflow.steps if s.id == dep_id), None)
                            activity_type = "generic"
                            if dep_step:
                                command = dep_step.command.lower()
                                if "dns" in command or "dig" in command or "nslookup" in command:
                                    activity_type = "dns"
                                elif "http" in command or "curl" in command or "wget" in command:
                                    activity_type = "http"
                                elif "scp" in command or "rsync" in command or "ftp" in command:
                                    activity_type = "file"
                            
                            # Create a particle for this connection
                            self.canvas.create_particle(conn_id, activity_type)
                            break
        
        # Handle completion if needed
        elif event == "complete" and status:
            # Could add completion effects here
            pass

    def create_menu_bar(self):
        """Create the application menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Workflow", command=self.new_workflow)
        file_menu.add_command(label="Open Workflow", command=self.open_workflow)
        file_menu.add_command(label="Save Workflow", command=self.save_workflow)
        file_menu.add_command(label="Save As...", command=self.save_workflow_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export Execution Log...", command=self.export_execution_log)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        self.templates_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Templates", menu=self.templates_menu)
        
        theme_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Theme", menu=theme_menu)
        theme_menu.add_command(label="Light Mode", command=lambda: self.set_theme("light"))
        theme_menu.add_command(label="Dark Mode", command=lambda: self.set_theme("dark"))

        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Preferences...", command=self.open_settings_panel)
        settings_menu.add_command(label="Toggle Animation", command=self.toggle_animation)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Workflow JSON Format Help", command=self.show_workflow_json_help)

    def load_templates(self):
        """Load templates from the templates directory and update the menu."""
        self.templates = {}
        self.templates_menu.delete(0, tk.END)
        
        try:
            for filename in sorted(os.listdir(self.templates_dir)):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.templates_dir, filename)
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        workflow = Workflow.from_dict(data)
                        self.templates[workflow.name] = workflow
        except Exception as e:
            self.show_error("Template Load Error", f"Failed to load templates: {e}")

        for name, template in self.templates.items():
            self.templates_menu.add_command(
                label=name,
                command=lambda t=template: self.load_template(t)
            )
        
        if self.templates:
            self.templates_menu.add_separator()
            
        self.templates_menu.add_command(label="Manage Templates...", command=self.open_template_manager)

    def open_template_manager(self):
        TemplateManager(self.root, self)

    def export_execution_log(self):
        """Export the execution log to a text file."""
        filename = filedialog.asksaveasfilename(
            title="Export Execution Log As",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            parent=self.root
        )
        if filename:
            try:
                log_content = self.log_text.get("1.0", tk.END)
                with open(filename, 'w') as f:
                    f.write(log_content)
                self.show_info("Success", "Execution log exported successfully")
            except Exception as e:
                self.show_error("Export Error", f"Failed to export log: {e}")

    def open_settings_panel(self):
        SettingsPanel(self.root, self)

    def set_theme(self, theme_name: str):
        if theme_name not in self.themes: return
        self.current_theme = theme_name
        colors = self.themes[theme_name].copy()  # Create a copy to modify
        
        # Adapt colors based on current context
        current_context = self._determine_current_context()
        if current_context == "reconnaissance":
            # Blue-themed colors for reconnaissance
            colors["node_pending"] = "#3A4A6A"
            colors["node_running"] = "#4A90E2"
            colors["node_success"] = "#3D6B4D"
            colors["conn_color"] = "#4A90E2"
        elif current_context == "exploitation":
            # Red-themed colors for exploitation
            colors["node_pending"] = "#7B4B4B"
            colors["node_running"] = "#D0021B"
            colors["node_success"] = "#3D6B4D"
            colors["conn_color"] = "#D0021B"
        elif current_context == "reporting":
            # Green-themed colors for reporting
            colors["node_pending"] = "#3D6B4D"
            colors["node_running"] = "#7ED321"
            colors["node_success"] = "#3D6B4D"
            colors["conn_color"] = "#7ED321"
        
        self.root.config(bg=colors["bg"])
        self.style.theme_use('default')
        self.style.configure('.', background=colors["bg"], foreground=colors["fg"], fieldbackground=colors["widget_bg"], troughcolor=colors["bg"])
        self.style.map('.', background=[('active', colors["widget_bg"])] , foreground=[('active', colors["fg"])] )
        for style_name in ['TFrame', 'TLabel', 'TLabelFrame', 'TLabelFrame.Label', 'TCheckbutton']:
            self.style.configure(style_name, background=colors["bg"], foreground=colors["fg"])
        self.style.configure('TButton', background=colors["widget_bg"], foreground=colors["fg"], borderwidth=1)
        self.style.map('TButton', background=[('active', colors["bg"])] , foreground=[('active', colors["fg"])] )
        self.style.configure('TEntry', fieldbackground=colors["widget_bg"], foreground=colors["widget_fg"], insertcolor=colors["fg"])
        self.style.configure('TNotebook', background=colors["bg"])
        self.style.configure('TNotebook.Tab', background=colors["widget_bg"], foreground=colors["fg"])
        self.style.map('TNotebook.Tab', background=[('selected', colors["bg"])] , foreground=[('selected', colors["fg"])] )
        for widget in [self.variables_text, self.log_text]:
            widget.config(bg=colors["widget_bg"], fg=colors["widget_fg"], insertbackground=colors["fg"],
                          selectbackground=colors["fg"], selectforeground=colors["bg"])
        self.canvas.config(bg=colors["canvas_bg"])
        self.update_workflow_display()
    
    def _determine_current_context(self) -> str:
        """Determine the current context based on workflow content and user preferences"""
        # First, check the current workflow for context clues
        if self.current_workflow:
            # Look for keywords in workflow name and step names
            workflow_text = (self.current_workflow.name + " " + 
                           " ".join([step.name for step in self.current_workflow.steps])).lower()
            
            if any(keyword in workflow_text for keyword in ["subfinder", "amass", "dns", "scan", "enum", "recon"]):
                return "reconnaissance"
            elif any(keyword in workflow_text for keyword in ["exploit", "payload", "attack", "vuln", "nmap"]):
                return "exploitation"
            elif any(keyword in workflow_text for keyword in ["report", "export", "document", "summary"]):
                return "reporting"
        
        # If no clear context from workflow, use recent user interactions
        recent_interactions = self.user_interactions[-10:]  # Last 10 interactions
        context_counts = {"reconnaissance": 0, "exploitation": 0, "reporting": 0}
        
        for interaction in recent_interactions:
            if interaction.context in context_counts:
                context_counts[interaction.context] += 1
        
        # Return the most frequent context
        if max(context_counts.values()) > 0:
            return max(context_counts, key=context_counts.get)
        
        # Default to general context
        return "general"

    def show_workflow_json_help(self):
        """Display a beautiful, comprehensive help dialog for workflow JSON format"""
        # Create a new top-level window for the help dialog
        help_window = tk.Toplevel(self.root)
        help_window.title("Workflow JSON Format Guide")
        help_window.geometry("900x700")
        help_window.resizable(True, True)
        help_window.transient(self.root)
        help_window.grab_set()
        
        # Apply theme colors
        colors = self.themes[self.current_theme]
        help_window.configure(bg=colors["bg"])
        
        # Create a notebook for tabbed interface
        notebook = ttk.Notebook(help_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Style for text widgets
        text_bg = colors["widget_bg"]
        text_fg = colors["widget_fg"]
        
        # TAB 1: Overview
        overview_frame = ttk.Frame(notebook)
        notebook.add(overview_frame, text="Overview")
        
        overview_text = scrolledtext.ScrolledText(overview_frame, wrap=tk.WORD, bg=text_bg, fg=text_fg, 
                                                 insertbackground=text_fg)
        overview_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        overview_content = """
Workflow Structure
==================

A workflow is a JSON object that defines a sequence of steps to execute. Each workflow consists of:

• Metadata (name, description, author, etc.)
• Global settings (execution mode, timeouts, environment variables)
• A list of steps to execute

Basic Workflow Structure:
------------------------
{
  "name": "Workflow Name",
  "description": "Brief description",
  "version": "1.0",
  "author": "Your Name",
  "tags": ["tag1", "tag2"],
  "execution_mode": "sequential",  // or "parallel"
  "global_timeout": 3600,
  "global_env_vars": {},
  "steps": [...]
}

Key Concepts:
------------
1. Variables: Use {VARIABLE_NAME} syntax in commands
2. Dependencies: Control execution order between steps
3. Environment Variables: Set per-step or globally
4. File Management: Define inputs and outputs for each step
        """
        overview_text.insert(tk.END, overview_content)
        overview_text.config(state=tk.DISABLED)
        
        # TAB 2: Workflow Fields
        workflow_frame = ttk.Frame(notebook)
        notebook.add(workflow_frame, text="Workflow Fields")
        
        workflow_text = scrolledtext.ScrolledText(workflow_frame, wrap=tk.WORD, bg=text_bg, fg=text_fg, 
                                                 insertbackground=text_fg)
        workflow_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        workflow_content = """
Workflow-Level Fields
=====================

Required Fields:
----------------
• name (string): The name of your workflow
• steps (array): Array of step objects to execute

Optional Fields:
----------------
• description (string): Detailed description of the workflow
• version (string): Version number (default: "1.0")
• author (string): Creator of the workflow
• tags (array): List of tags for categorization
• execution_mode (string): "sequential" or "parallel" (default: "sequential")
• global_timeout (integer): Maximum execution time in seconds (default: 3600)
• global_env_vars (object): Environment variables available to all steps
• created_at (string): ISO timestamp (auto-generated)
• modified_at (string): ISO timestamp (auto-generated)

Example:
--------
{
  "name": "Subdomain Enumeration",
  "description": "Discover subdomains using multiple tools",
  "version": "1.0",
  "author": "Security Team",
  "tags": ["recon", "subdomain", "enumeration"],
  "execution_mode": "sequential",
  "global_timeout": 7200,
  "global_env_vars": {
    "TARGET": "example.com",
    "OUTPUT_DIR": "/tmp/recon"
  }
}
        """
        workflow_text.insert(tk.END, workflow_content)
        workflow_text.config(state=tk.DISABLED)
        
        # TAB 3: Step Fields
        step_frame = ttk.Frame(notebook)
        notebook.add(step_frame, text="Step Fields")
        
        step_text = scrolledtext.ScrolledText(step_frame, wrap=tk.WORD, bg=text_bg, fg=text_fg, 
                                             insertbackground=text_fg)
        step_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        step_content = """
Step Object Fields
==================

Required Fields:
----------------
• name (string): Descriptive name for the step
• command (string): Shell command to execute

Optional Fields:
----------------
• id (string): Unique identifier (auto-generated if not provided)
• description (string): Detailed explanation of what the step does
• working_directory (string): Directory to execute the command in
• environment_vars (object): Step-specific environment variables
• input_files (array): List of file paths required by this step
• output_files (array): List of file paths produced by this step
• timeout (integer): Maximum execution time in seconds (default: 300)
• retry_count (integer): Number of retry attempts on failure (default: 0)
• dependencies (array): List of step IDs that must complete before this one
• enabled (boolean): Whether to execute this step (default: true)
• step_type (string): Type of step - "shell", "python", or "docker" (default: "shell")
• custom_script (string): Custom code for python/docker steps
• notes (string): Additional notes about the step
• pos_x, pos_y (integers): Canvas position coordinates

Example Step:
-------------
{
  "name": "Subfinder Scan",
  "description": "Use subfinder to discover subdomains",
  "command": "subfinder -d {TARGET} -o {OUTPUT_DIR}/subfinder.txt",
  "working_directory": "{OUTPUT_DIR}",
  "environment_vars": {
    "SUBFINDER_TIMEOUT": "300"
  },
  "input_files": [],
  "output_files": ["{OUTPUT_DIR}/subfinder.txt"],
  "timeout": 600,
  "retry_count": 1,
  "dependencies": [],
  "enabled": true,
  "step_type": "shell",
  "notes": "Requires subfinder to be installed"
}
        """
        step_text.insert(tk.END, step_content)
        step_text.config(state=tk.DISABLED)
        
        # TAB 4: Complete Example
        example_frame = ttk.Frame(notebook)
        notebook.add(example_frame, text="Complete Example")
        
        example_text = scrolledtext.ScrolledText(example_frame, wrap=tk.WORD, bg=text_bg, fg=text_fg, 
                                                insertbackground=text_fg)
        example_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        example_content = """
Complete Workflow Example
=========================

{
  "name": "Web Application Recon",
  "description": "Comprehensive web application reconnaissance workflow",
  "version": "1.0",
  "author": "Bug Bounty Hunter",
  "tags": ["web", "recon", "enumeration"],
  "execution_mode": "sequential",
  "global_timeout": 10800,
  "global_env_vars": {
    "TARGET": "example.com",
    "OUTPUT_DIR": "/tmp/web_recon"
  },
  "steps": [
    {
      "id": "step1",
      "name": "Subdomain Enumeration",
      "description": "Discover subdomains using subfinder",
      "command": "subfinder -d {TARGET} -o {OUTPUT_DIR}/subdomains.txt",
      "working_directory": "{OUTPUT_DIR}",
      "environment_vars": {},
      "input_files": [],
      "output_files": ["{OUTPUT_DIR}/subdomains.txt"],
      "timeout": 600,
      "retry_count": 1,
      "dependencies": [],
      "enabled": true,
      "step_type": "shell",
      "custom_script": "",
      "notes": "Requires subfinder tool",
      "pos_x": 50,
      "pos_y": 50
    },
    {
      "id": "step2",
      "name": "HTTP Probing",
      "description": "Check which subdomains are alive",
      "command": "httpx -l {OUTPUT_DIR}/subdomains.txt -o {OUTPUT_DIR}/alive.txt",
      "working_directory": "{OUTPUT_DIR}",
      "environment_vars": {},
      "input_files": ["{OUTPUT_DIR}/subdomains.txt"],
      "output_files": ["{OUTPUT_DIR}/alive.txt"],
      "timeout": 900,
      "retry_count": 1,
      "dependencies": ["step1"],
      "enabled": true,
      "step_type": "shell",
      "custom_script": "",
      "notes": "Requires httpx tool",
      "pos_x": 300,
      "pos_y": 50
    },
    {
      "id": "step3",
      "name": "Screenshot Capture",
      "description": "Take screenshots of alive subdomains",
      "command": "aquatone -hosts {OUTPUT_DIR}/alive.txt -out {OUTPUT_DIR}/aquatone",
      "working_directory": "{OUTPUT_DIR}",
      "environment_vars": {},
      "input_files": ["{OUTPUT_DIR}/alive.txt"],
      "output_files": ["{OUTPUT_DIR}/aquatone"],
      "timeout": 1200,
      "retry_count": 0,
      "dependencies": ["step2"],
      "enabled": true,
      "step_type": "shell",
      "custom_script": "",
      "notes": "Requires aquatone tool",
      "pos_x": 550,
      "pos_y": 50
    }
  ]
}
        """
        example_text.insert(tk.END, example_content)
        example_text.config(state=tk.DISABLED)
        
        # TAB 5: Tips & Best Practices
        tips_frame = ttk.Frame(notebook)
        notebook.add(tips_frame, text="Tips & Best Practices")
        
        tips_text = scrolledtext.ScrolledText(tips_frame, wrap=tk.WORD, bg=text_bg, fg=text_fg, 
                                             insertbackground=text_fg)
        tips_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tips_content = """
Tips & Best Practices
=====================

1. Variable Usage:
   • Use {VARIABLE_NAME} syntax for dynamic values
   • Define global variables in global_env_vars
   • Use step-specific variables in environment_vars

2. Dependencies:
   • Use step IDs in dependencies array
   • Ensure no circular dependencies
   • Sequential mode executes steps in order
   • Parallel mode executes independent steps concurrently

3. Error Handling:
   • Set appropriate timeout values
   • Use retry_count for flaky steps
   • Disable experimental steps with enabled: false
   • Add notes for troubleshooting

4. File Management:
   • Specify input_files for dependency tracking
   • List output_files for cleanup/reference
   • Use consistent directory structure

5. Organization:
   • Use descriptive names and descriptions
   • Group related steps together
   • Add tags for categorization
   • Include version information

6. Security:
   • Avoid hardcoding sensitive information
   • Use environment variables for secrets
   • Validate file paths
   • Limit working directories

7. Testing:
   • Use dry run feature to validate workflows
   • Test with simple commands first
   • Validate JSON syntax before saving
   • Use templates for common workflows
        """
        tips_text.insert(tk.END, tips_content)
        tips_text.config(state=tk.DISABLED)
        
        # Add a close button
        button_frame = ttk.Frame(help_window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        close_btn = ttk.Button(button_frame, text="Close", command=help_window.destroy)
        close_btn.pack(side=tk.RIGHT)

    def on_workflow_name_changed(self, *args):
        self.current_workflow.name = self.workflow_name_var.get()
    
    def on_workflow_desc_changed(self, *args):
        self.current_workflow.description = self.workflow_desc_var.get()

    def on_global_vars_changed(self, *args):
        try:
            vars_text = self.global_vars_text.get("1.0", tk.END).strip()
            if not vars_text:
                self.current_workflow.global_env_vars = {}
                return

            lines = vars_text.split('\n')
            global_vars = {}
            for line in lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    global_vars[key.strip()] = value.strip()
            self.current_workflow.global_env_vars = global_vars
            self.global_vars_text.edit_modified(False) # Reset modified flag
        except Exception as e:
            logger.error(f"Error parsing global variables: {e}")
    
    def update_workflow_display(self):
        """Update the workflow display"""
        self.workflow_name_var.set(self.current_workflow.name)
        self.workflow_desc_var.set(self.current_workflow.description)
        vars_text = "\n".join([f"{k}={v}" for k, v in self.current_workflow.global_env_vars.items()])
        self.global_vars_text.delete("1.0", tk.END)
        self.global_vars_text.insert("1.0", vars_text)
        self.global_vars_text.edit_modified(False)
        self.canvas.render_workflow(self.current_workflow)
        
        # Update recommendations based on current context
        if self.adaptive_interface_enabled:
            current_context = self._determine_current_context()
            self._update_recommendations_panel(current_context)
    
    def add_step(self):
        """Add a new step to the workflow"""
        new_step = WorkflowStep(name=f"Step {len(self.current_workflow.steps) + 1}")
        editor = WorkflowEditor(self.root, new_step, self.current_workflow)
        self.root.wait_window(editor)
        
        if new_step.name:
            self.current_workflow.steps.append(new_step)
            self.update_workflow_display()
            # Track this interaction
            self.track_user_interaction("step_added", new_step.name)
    
    def edit_step(self, step_id: Optional[str] = None):
        """Edit selected step"""
        if not step_id: step_id = self.selected_step_id
        if not step_id:
            self.show_warning("No Selection", "Please select a step to edit")
            return
        
        step = next((s for s in self.current_workflow.steps if s.id == step_id), None)
        if step:
            editor = WorkflowEditor(self.root, step, self.current_workflow)
            self.root.wait_window(editor)
            self.update_workflow_display()
    
    def delete_step(self):
        """Delete selected step"""
        if not self.selected_step_id:
            self.show_warning("No Selection", "Please select a step to delete")
            return
        
        step_id = self.selected_step_id
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this step?", parent=self.root):
            self.current_workflow.steps = [s for s in self.current_workflow.steps if s.id != step_id]
            for s in self.current_workflow.steps:
                if step_id in s.dependencies:
                    s.dependencies.remove(step_id)
            self.update_workflow_display()

    def delete_selected_steps(self):
        """Delete all selected steps."""
        if not self.canvas.selected_node_ids:
            self.show_warning("No Selection", "Please select steps to delete")
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {len(self.canvas.selected_node_ids)} steps?", parent=self.root):
            for step_id in list(self.canvas.selected_node_ids):
                self.current_workflow.steps = [s for s in self.current_workflow.steps if s.id != step_id]
                for s in self.current_workflow.steps:
                    if step_id in s.dependencies:
                        s.dependencies.remove(step_id)
            self.canvas.selected_node_ids.clear()
            self.update_workflow_display()

    def toggle_selected_steps_enabled(self):
        """Toggle the enabled state of all selected steps."""
        if not self.canvas.selected_node_ids:
            self.show_warning("No Selection", "Please select steps to toggle")
            return

        for step_id in self.canvas.selected_node_ids:
            self.canvas.toggle_step_enabled(step_id)

    def duplicate_step(self, step_id: str):
        """Duplicate the selected step."""
        original_step = next((s for s in self.current_workflow.steps if s.id == step_id), None)
        if not original_step:
            return

        new_step = copy.deepcopy(original_step)
        new_step.id = str(uuid.uuid4())
        new_step.name = f"Copy of {original_step.name}"
        new_step.pos_x += 40
        new_step.pos_y += 40

        self.current_workflow.steps.append(new_step)
        self.update_workflow_display()

    def run_from_step(self, step_id: str):
        """Run the workflow starting from a specific step."""
        try:
            start_index = next(i for i, s in enumerate(self.current_workflow.steps) if s.id == step_id)
        except StopIteration:
            self.show_error("Step Not Found", f"Could not find step with ID {step_id} to run from.")
            return

        # Create a new workflow with a subset of steps
        run_workflow = copy.deepcopy(self.current_workflow)
        run_workflow.steps = self.current_workflow.steps[start_index:]

        # Clear dependencies for the first step
        if run_workflow.steps:
            run_workflow.steps[0].dependencies = []

        self.run_workflow(dry_run=False, workflow=run_workflow)
    
    def new_workflow(self):
        """Create a new workflow"""
        if messagebox.askyesno("New Workflow", "Are you sure? Unsaved changes will be lost.", parent=self.root):
            self.current_workflow = Workflow()
            self.current_filepath = None
            self.update_workflow_display()
            self.clear_log()
    
    def open_workflow(self):
        """Open workflow from file"""
        filename = filedialog.askopenfilename(
            title="Open Workflow",
            filetypes=[("JSON files", "*.json"), ("YAML files", "*.yaml"), ("All files", "*.* ")],
            parent=self.root
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    data = yaml.safe_load(f) if filename.endswith(('.yaml', '.yml')) else json.load(f)
                self.current_workflow = Workflow.from_dict(data)
                self.current_filepath = filename
                self.update_workflow_display()
                self.clear_log()
                self.show_info("Success", "Workflow loaded successfully")
            except Exception as e:
                self.show_error("Load Error", f"Failed to load workflow: {e}")
    
    def save_workflow(self):
        """Save current workflow"""
        if not self.current_filepath:
            return self.save_workflow_as()

        try:
            data = self.current_workflow.to_dict()
            with open(self.current_filepath, 'w') as f:
                if self.current_filepath.endswith(('.yaml', '.yml')):
                    yaml.dump(data, f, default_flow_style=False)
                else:
                    json.dump(data, f, indent=2)
            self.last_saved_label.config(text=f"Last saved: {datetime.now().strftime('%H:%M:%S')}")
            self.show_info("Success", "Workflow saved successfully")
        except Exception as e:
            self.show_error("Save Error", f"Failed to save workflow: {e}")
    
    def save_workflow_as(self):
        """Save current workflow to a new file"""
        filename = filedialog.asksaveasfilename(
            title="Save Workflow As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("YAML files", "*.yaml")],
            parent=self.root
        )
        if filename:
            self.current_filepath = filename
            self.save_workflow()
    
    def load_template(self, template: Workflow):
        """Load a workflow template"""
        if messagebox.askyesno("Load Template", f"Load template '{template.name}'? Unsaved changes will be lost.", parent=self.root):
            new_workflow = Workflow.from_dict(template.to_dict())
            
            id_map = {step.id: str(uuid.uuid4()) for step in new_workflow.steps}
            new_workflow.id = str(uuid.uuid4())
            for step in new_workflow.steps:
                step.id = id_map.get(step.id, str(uuid.uuid4()))
                step.dependencies = [id_map[dep_id] for dep_id in step.dependencies if dep_id in id_map]

            self.current_workflow = new_workflow
            self.update_workflow_display()
            self.clear_log()
            # Track this interaction
            self.track_user_interaction("template_used", template.name)
    
    def parse_variables(self) -> Dict[str, str]:
        """Parse variables from the variables text field"""
        try:
            return {k.strip(): v.strip() for line in self.variables_text.get("1.0", tk.END).strip().split("\n") if "=" in line for k, v in [line.split("=", 1)]}
        except Exception as e:
            self.show_error("Variable Parse Error", f"Failed to parse variables: {e}")
            return {}
    
    def run_workflow(self, dry_run: bool, workflow: Optional[Workflow] = None):
        if workflow is None:
            workflow = self.current_workflow

        if not workflow.steps:
            self.show_warning("No Steps", "Workflow has no steps to execute")
            return
        
        if not dry_run and not messagebox.askyesno("Execute Workflow", "Are you sure you want to execute this workflow?", parent=self.root):
            return
            
        self.update_workflow_display()
        variables = self.parse_variables()
        self.runner = WorkflowRunner(dry_run=dry_run)
        self.runner.set_status_callback(self.on_step_status_update)
        self.runner.set_animation_callback(self.on_step_animation_update)
        
        # Start animation if enabled
        if self.animation_enabled and self.canvas:
            self.canvas.start_animation()
        
        def run_in_thread():
            mode = "Dry run" if dry_run else "Execution"
            try:
                self.log_message(f"Starting workflow {mode.lower()}...")
                results = self.runner.execute_workflow(workflow, workflow.global_env_vars, variables)
                self.display_results(results)
                self.log_message(f"Workflow {mode.lower()} completed")
            except Exception as e:
                self.log_message(f"Workflow {mode.lower()} failed: {e}")
                self.show_error(f"Workflow {mode} Error", f"Workflow {mode.lower()} failed: {e}")
        
        threading.Thread(target=run_in_thread, daemon=True).start()

    def dry_run_workflow(self):
        self.run_workflow(dry_run=True, workflow=self.current_workflow)
    
    def execute_workflow(self):
        self.run_workflow(dry_run=False, workflow=self.current_workflow)
        
    def on_step_status_update(self, step_id: Optional[str], status: Optional[StepStatus], message: str):
        """Callback to update UI on step status change."""
        self.log_message(message)
        if step_id and status:
            self.canvas.update_node_status(step_id, status)
        self.root.update_idletasks()

    def abort_execution(self):
        """Abort current execution"""
        if self.runner.running:
            self.runner.abort()
            self.log_message("Execution aborted by user")
            
        # Stop animation when execution is aborted
        if self.canvas and self.animation_enabled:
            self.canvas.stop_animation()

    def restart_application(self):
        """Restart the application."""
        python = sys.executable
        os.execl(python, python, *sys.argv)
    
    def toggle_animation(self):
        """Toggle the neural network animation on/off"""
        self.animation_enabled = not self.animation_enabled
        if not self.animation_enabled and self.canvas:
            self.canvas.stop_animation()
        # Track this interaction
        self.track_user_interaction("ui_element_used", "toggle_animation", "general")
        # Save the setting
        self.save_settings()
    
    def toggle_adaptive_interface(self):
        """Toggle the adaptive neural interface on/off"""
        self.adaptive_interface_enabled = not self.adaptive_interface_enabled
        # Track this interaction
        self.track_user_interaction("ui_element_used", "toggle_adaptive_interface", "general")
        # Save the setting
        self.save_settings()
    
    def display_results(self, results: Dict[str, ExecutionResult]):
        """Display execution results in the log"""
        # Stop animation when execution is complete
        if self.canvas and self.animation_enabled:
            self.canvas.stop_animation()
            
        self.log_message("\n=== Execution Results ===")
        for step_id, result in results.items():
            step_name = next((s.name for s in self.current_workflow.steps if s.id == step_id), "Unknown")
            self.log_message(f"Step: {step_name} | Status: {result.status.value} | Time: {result.execution_time:.2f}s")
            if result.stdout:
                self.log_message(f"  Output: {result.stdout[:200].strip()}{'...' if len(result.stdout) > 200 else ''}")
            if result.stderr:
                self.log_message(f"  Error: {result.stderr[:200].strip()}{'...' if len(result.stderr) > 200 else ''}")
            if result.error_message:
                self.log_message(f"  Info: {result.error_message}")
    
    def log_message(self, message: str):
        """Add message to the execution log"""
        def append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, append)
    
    def clear_log(self):
        """Clear the execution log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Stop animation when clearing the log
        if self.canvas and self.animation_enabled:
            self.canvas.stop_animation()
    
    def run(self):
        """Start the application"""
        self.root.wait_window(self.loading_screen.root) # Wait for loading screen to close
        self.root.deiconify() # Show the main window
        self.root.mainloop()