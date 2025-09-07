"""
Workflow canvas for the Workflow Generator application.
Contains the WorkflowCanvas and WorkflowCanvasNode classes.
"""

import tkinter as tk
from typing import Dict, List, Optional, Any
import random
import uuid

from models import WorkflowStep, Workflow, StepStatus, Particle


class WorkflowCanvasNode:
    """Represents a node on the visual workflow designer canvas."""
    def __init__(self, canvas: 'WorkflowCanvas', step: WorkflowStep):
        self.canvas = canvas
        self.step = step
        self.width = 180
        self.height = 60
        
        colors = self.canvas.app.themes[self.canvas.app.current_theme]
        
        self.rect_id = self.canvas.create_rectangle(
            self.step.pos_x, self.step.pos_y, self.step.pos_x + self.width, self.step.pos_y + self.height,
            fill=colors["node_pending"], outline=colors["node_outline"], width=2, tags="node"
        )
        self.text_id = self.canvas.create_text(
            self.step.pos_x + self.width / 2, self.step.pos_y + self.height / 2,
            text=self.step.name, width=self.width - 10, tags="node_text", fill=colors["node_text"]
        )
        
        self.canvas.tag_bind(self.rect_id, "<ButtonPress-1>", self.on_press)
        self.canvas.tag_bind(self.rect_id, "<B1-Motion>", self.on_drag)
        self.canvas.tag_bind(self.rect_id, "<Double-Button-1>", self.on_double_click)
        self.canvas.tag_bind(self.text_id, "<ButtonPress-1>", self.on_press)
        self.canvas.tag_bind(self.text_id, "<B1-Motion>", self.on_drag)
        self.canvas.tag_bind(self.text_id, "<Double-Button-1>", self.on_double_click)
        
        self._drag_data = {"x": 0, "y": 0}
        self.update_enabled_state()

    def update_enabled_state(self):
        """Update the visual state of the node based on its enabled status."""
        colors = self.canvas.app.themes[self.canvas.app.current_theme]
        if self.step.enabled:
            self.canvas.itemconfig(self.rect_id, outline=colors["node_outline"])
        else:
            self.canvas.itemconfig(self.rect_id, outline="grey", dash=(4, 4))

    def on_press(self, event):
        self._drag_data["x"] = self.canvas.canvasx(event.x)
        self._drag_data["y"] = self.canvas.canvasy(event.y)
        self.canvas.select_node(self.step.id, event.state & 0x0004) # Check for Control key

    def on_drag(self, event):
        dx = self.canvas.canvasx(event.x) - self._drag_data["x"]
        dy = self.canvas.canvasy(event.y) - self._drag_data["y"]

        for node_id in self.canvas.selected_node_ids:
            node = self.canvas.nodes[node_id]
            self.canvas.move(node.rect_id, dx, dy)
            self.canvas.move(node.text_id, dx, dy)
            node.step.pos_x += dx
            node.step.pos_y += dy
            # Update original coordinates for proper zooming
            self.canvas.update_original_coords_for_node(node.step.id)

        self._drag_data["x"] = self.canvas.canvasx(event.x)
        self._drag_data["y"] = self.canvas.canvasy(event.y)
        self.canvas.update_scroll_region()

    def on_double_click(self, event):
        self.canvas.app.edit_step(self.step.id)

    def update_status(self, status: StepStatus):
        colors = self.canvas.app.themes[self.canvas.app.current_theme]
        color_map = {
            StepStatus.PENDING: colors["node_pending"], StepStatus.RUNNING: colors["node_running"],
            StepStatus.SUCCESS: colors["node_success"], StepStatus.FAILED: colors["node_failed"],
            StepStatus.SKIPPED: colors["node_skipped"], StepStatus.TIMEOUT: colors["node_timeout"]
        }
        self.canvas.itemconfig(self.rect_id, fill=color_map.get(status, colors["canvas_bg"]))
        
    def update_text(self):
        self.canvas.itemconfig(self.text_id, text=self.step.name)


class WorkflowCanvas(tk.Canvas):
    """A drag-and-drop canvas for designing workflows."""

    def zoom_in(self):
        self.zoom(1.1)

    def zoom_out(self):
        self.zoom(0.9)

    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.rescale_canvas()

    def zoom(self, event_or_factor):
        if isinstance(event_or_factor, float):
            factor = event_or_factor
        else: # Mouse wheel event
            if event_or_factor.delta > 0:
                factor = 1.1
            else:
                factor = 0.9
        
        self.zoom_factor *= factor
        self.rescale_canvas()

    def rescale_canvas(self):
        for item_id, original_coords in self.original_coords.items():
            new_coords = [c * self.zoom_factor for c in original_coords]
            self.coords(item_id, *new_coords)

            if "node_text" in self.gettags(item_id):
                font_size = int(10 * self.zoom_factor)
                if font_size < 1:
                    font_size = 1
                self.itemconfig(item_id, font=("Courier", font_size))

    def update_original_coords_for_node(self, step_id):
        """Update original coordinates for a node after it has been moved."""
        if step_id not in self.nodes:
            return
            
        node = self.nodes[step_id]
        
        # Update rectangle coordinates
        rect_coords = self.coords(node.rect_id)
        self.original_coords[node.rect_id] = tuple(rect_coords)
        
        # Update text coordinates
        text_coords = self.coords(node.text_id)
        self.original_coords[node.text_id] = tuple(text_coords)
        
        # Update connection coordinates
        self.update_connections_for_node(step_id)

    def update_all_original_coords(self):
        """Update original coordinates for all nodes and connections."""
        # Update node coordinates
        for step_id, node in self.nodes.items():
            self.original_coords[node.rect_id] = (
                node.step.pos_x, 
                node.step.pos_y, 
                node.step.pos_x + node.width, 
                node.step.pos_y + node.height
            )
            self.original_coords[node.text_id] = (
                node.step.pos_x + node.width / 2, 
                node.step.pos_y + node.height / 2
            )
        
        # Update connection coordinates
        for step in self.app.current_workflow.steps:
            if step.id not in self.nodes: 
                continue
            for dep_id in step.dependencies:
                if dep_id in self.nodes:
                    # We need to find the connection line and update its coordinates
                    from_node = self.nodes[dep_id]
                    to_node = self.nodes[step.id]
                    line_coords = (
                        from_node.step.pos_x + from_node.width, from_node.step.pos_y + from_node.height / 2,
                        to_node.step.pos_x, to_node.step.pos_y + to_node.height / 2
                    )
                    # Find the line in our connections
                    for conn_id in self.connections:
                        tags = self.gettags(conn_id)
                        if f"conn-from-{dep_id}" in tags and f"conn-to-{step.id}" in tags:
                            self.original_coords[conn_id] = line_coords
                            break

    def __init__(self, parent, app):
        super().__init__(parent, bg=app.themes[app.current_theme]["canvas_bg"], highlightthickness=0)
        self.app = app
        self.nodes: Dict[str, WorkflowCanvasNode] = {}
        self.connections = []
        self.selected_node_id: Optional[str] = None
        self.selected_node_ids: set[str] = set()
        
        # Particle animation system
        self.particles: Dict[str, 'Particle'] = {}
        self.particle_items: Dict[str, int] = {}  # particle_id -> canvas_item_id
        self.animation_running = False
        self.animation_job = None
        
        self.connection_start_node = None
        self.connection_preview_line = None
        self.zoom_factor = 1.0
        self.original_coords = {}

        self.bind("<Shift-ButtonPress-1>", self.start_connection)
        self.bind("<Shift-B1-Motion>", self.draw_connection_preview)
        self.bind("<Shift-ButtonRelease-1>", self.end_connection)
        self.bind("<Control-MouseWheel>", self.zoom)
        self.bind("<Button-3>", self.show_context_menu)
        
    def start_animation(self):
        """Start the particle animation system"""
        if not self.animation_running:
            self.animation_running = True
            self.animate_particles()
    
    def stop_animation(self):
        """Stop the particle animation system"""
        self.animation_running = False
        if self.animation_job:
            self.after_cancel(self.animation_job)
            self.animation_job = None
        # Clear all particles
        for item_id in self.particle_items.values():
            self.delete(item_id)
        self.particle_items.clear()
        self.particles.clear()
    
    def animate_particles(self):
        """Main animation loop for particles"""
        if not self.animation_running:
            return
            
        # Update particle positions
        particles_to_remove = []
        for particle_id, particle in list(self.particles.items()):
            # Move particle along connection, adjusted by animation speed
            particle.progress += particle.speed * getattr(self.app, 'animation_speed', 1.0)
            
            # Get connection coordinates
            conn_coords = self.original_coords.get(particle.connection_id)
            if not conn_coords:
                particles_to_remove.append(particle_id)
                continue
                
            x1, y1, x2, y2 = conn_coords
            # Calculate new position based on progress
            particle.x = x1 + (x2 - x1) * particle.progress
            particle.y = y1 + (y2 - y1) * particle.progress
            
            # Draw particle
            self.draw_particle(particle)
            
            # Remove particles that have completed their journey
            if particle.progress >= 1.0:
                particles_to_remove.append(particle_id)
                # For guidance particles, create a new one to maintain continuous guidance
                if particle.particle_type == "guidance":
                    self.create_particle(particle.connection_id, particle.activity_type, "guidance")
        
        # Remove completed particles
        for particle_id in particles_to_remove:
            if particle_id in self.particle_items:
                self.delete(self.particle_items[particle_id])
                del self.particle_items[particle_id]
            if particle_id in self.particles:
                del self.particles[particle_id]
                
        # Schedule next animation frame
        # Adjust animation speed (higher speed = faster animation = shorter delay)
        delay = int(50 / getattr(self.app, 'animation_speed', 1.0))
        delay = max(10, min(100, delay))  # Keep delay between 10ms and 100ms
        self.animation_job = self.after(delay, self.animate_particles)
    
    def draw_particle(self, particle):
        """Draw a particle on the canvas"""
        # Remove existing particle item if it exists
        if particle.id in self.particle_items:
            self.delete(self.particle_items[particle.id])
            
        # Create new particle item based on shape
        colors = self.app.themes[self.app.current_theme]
        particle_color = particle.color if particle.color else colors["conn_color"]
        
        if particle.shape == "square":
            item_id = self.create_rectangle(
                particle.x - particle.size/2, particle.y - particle.size/2,
                particle.x + particle.size/2, particle.y + particle.size/2,
                fill=particle_color, outline=""
            )
        elif particle.shape == "diamond":
            item_id = self.create_polygon(
                particle.x, particle.y - particle.size/2,
                particle.x + particle.size/2, particle.y,
                particle.x, particle.y + particle.size/2,
                particle.x - particle.size/2, particle.y,
                fill=particle_color, outline=""
            )
        else:  # circle (default)
            item_id = self.create_oval(
                particle.x - particle.size/2, particle.y - particle.size/2,
                particle.x + particle.size/2, particle.y + particle.size/2,
                fill=particle_color, outline=""
            )
            
        self.particle_items[particle.id] = item_id
    
    def create_particle(self, connection_id: str, activity_type: str = "generic", particle_type: str = "data"):
        """Create a new particle for animation"""
        import uuid
        
        # Get connection coordinates
        conn_coords = self.original_coords.get(connection_id)
        if not conn_coords:
            return None
            
        x1, y1, x2, y2 = conn_coords
        
        # Determine particle properties based on activity type
        colors = self.app.themes[self.app.current_theme]
        if activity_type == "dns":
            color = "#4A90E2"  # Blue for DNS
            shape = "circle"
        elif activity_type == "http":
            color = "#F5A623"  # Yellow for HTTP
            shape = "square"
        elif activity_type == "file":
            color = "#D0021B"  # Red for file transfers
            shape = "diamond"
        else:
            color = colors["conn_color"]  # Default connection color
            shape = "circle"
            
        # For guidance particles, use a different appearance
        if particle_type == "guidance":
            color = "#7ED321"  # Green for guidance
            shape = "circle"
            size = 6  # Larger for visibility
        else:
            size = 4 + random.random() * 4  # Random size between 4 and 8
            
        particle = Particle(
            id=str(uuid.uuid4()),
            x=x1,
            y=y1,
            connection_id=connection_id,
            progress=0.0,
            speed=0.02 + random.random() * 0.03,  # Random speed between 0.02 and 0.05
            color=color,
            size=size,
            shape=shape,
            activity_type=activity_type,
            particle_type=particle_type
        )
        
        self.particles[particle.id] = particle
        return particle
    
    def create_guidance_particles(self, context: str = "general"):
        """Create guidance particles to anticipate user's next steps"""
        if not self.app.adaptive_interface_enabled:
            return
            
        # Create subtle guidance particles on frequently used connections
        for conn_id in self.connections[:3]:  # Limit to first 3 connections
            # Create a guidance particle with slower speed for subtlety
            particle = Particle(
                id=str(uuid.uuid4()),
                x=0,  # Will be set based on connection
                y=0,  # Will be set based on connection
                connection_id=conn_id,
                progress=0.0,
                speed=0.01,  # Slow speed for subtlety
                color="#7ED321",  # Green for guidance
                size=6,
                shape="circle",
                activity_type="guidance",
                particle_type="guidance"
            )
            
            # Set initial position based on connection
            conn_coords = self.original_coords.get(conn_id)
            if conn_coords:
                x1, y1, x2, y2 = conn_coords
                particle.x = x1
                particle.y = y1
            
            self.particles[particle.id] = particle

    def show_context_menu(self, event):
        """Display a context menu on right-click."""
        context_menu = tk.Menu(self, tearoff=0)
        node = self.get_node_at_pos(event.x, event.y)

        if node and node.step.id in self.selected_node_ids:
            if len(self.selected_node_ids) > 1:
                context_menu.add_command(label="Delete Selected Steps", command=self.app.delete_selected_steps)
                context_menu.add_command(label="Toggle Enabled/Disabled", command=self.app.toggle_selected_steps_enabled)
            else:
                context_menu.add_command(label="Edit Step", command=lambda: self.app.edit_step(node.step.id))
                context_menu.add_command(label="Delete Step", command=self.app.delete_step)
                context_menu.add_separator()
                context_menu.add_command(label="Duplicate Step", command=lambda: self.app.duplicate_step(node.step.id))
                context_menu.add_command(label="Run from Here", command=lambda: self.app.run_from_step(node.step.id))
                context_menu.add_separator()
                context_menu.add_command(label="Toggle Enabled", command=lambda: self.toggle_step_enabled(node.step.id))
        else:
            context_menu.add_command(label="Add Step", command=self.app.add_step)

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
        self.bind("<Button-3>", self.show_context_menu)

    def toggle_step_enabled(self, step_id: str):
        """Toggle the enabled state of a step."""
        step = next((s for s in self.app.current_workflow.steps if s.id == step_id), None)
        if step:
            step.enabled = not step.enabled
            self.nodes[step_id].update_enabled_state()

    def get_node_at_pos(self, x: int, y: int) -> Optional[WorkflowCanvasNode]:
        """Find the node under the cursor."""
        items = self.find_overlapping(x, y, x, y)
        if not items:
            return None
        
        node_rect_id = None
        for item in reversed(items):
            if "node" in self.gettags(item):
                node_rect_id = item
                break
        
        if node_rect_id:
            for node in self.nodes.values():
                if node.rect_id == node_rect_id:
                    return node
        return None

    def start_connection(self, event):
        node = self.get_node_at_pos(event.x, event.y)
        if node:
            self.connection_start_node = node
            self.config(cursor="crosshair")

    def draw_connection_preview(self, event):
        if not self.connection_start_node:
            return
        
        if self.connection_preview_line:
            self.delete(self.connection_preview_line)
            self.connection_preview_line = None
            
        start_node = self.connection_start_node
        colors = self.app.themes[self.app.current_theme]
        
        self.connection_preview_line = self.create_line(
            start_node.step.pos_x + start_node.width / 2,
            start_node.step.pos_y + start_node.height / 2,
            event.x,
            event.y,
            fill=colors["conn_color"],
            dash=(4, 4),
            width=2
        )

    def end_connection(self, event):
        self.config(cursor="")
        
        if self.connection_preview_line:
            self.delete(self.connection_preview_line)
            self.connection_preview_line = None

        if not self.connection_start_node:
            return

        start_node = self.connection_start_node
        end_node = self.get_node_at_pos(event.x, event.y)
        self.connection_start_node = None

        if end_node and end_node != start_node:
            if self.is_circular_dependency(start_node.step, end_node.step):
                self.app.show_warning("Invalid Connection", "This connection would create a circular dependency.")
                return
            
            if start_node.step.id not in end_node.step.dependencies:
                end_node.step.dependencies.append(start_node.step.id)
                self.draw_all_connections()

    def is_circular_dependency(self, start_step: WorkflowStep, end_step: WorkflowStep) -> bool:
        """Check if making end_step dependent on start_step creates a cycle."""
        q = [end_step.id]
        visited = {end_step.id}
        
        while q:
            current_id = q.pop(0)
            if current_id == start_step.id:
                return True
                
            current_step = next((s for s in self.app.current_workflow.steps if s.id == current_id), None)
            if not current_step: continue
                
            for dep_id in current_step.dependencies:
                if dep_id not in visited:
                    visited.add(dep_id)
                    q.append(dep_id)
        return False

    def update_scroll_region(self):
        bbox = self.bbox("all")
        if bbox:
            self.config(scrollregion=bbox)
        else:
            self.config(scrollregion=(0, 0, self.winfo_width(), self.winfo_height()))

    def render_workflow(self, workflow: Workflow):
        self.delete("all")
        self.nodes = {}
        self.connections = []

        positions = {(s.pos_x, s.pos_y) for s in workflow.steps}
        has_layout_info = len(positions) > 1 or len(workflow.steps) <= 1
        
        for step in workflow.steps:
            self.nodes[step.id] = WorkflowCanvasNode(self, step)

        if not has_layout_info:
            self.auto_layout()
        
        # Initialize original coordinates for all nodes and connections
        self.update_all_original_coords()
        self.draw_all_connections()
        self.select_node(self.selected_node_id)
        self.update_scroll_region()

    def auto_layout(self):
        """Arranges nodes in a simple grid layout if no position data is provided."""
        if not self.nodes:
            return

        x, y = 50, 50
        canvas_width = self.winfo_width() if self.winfo_width() > 1 else 1000
        node_width = 180
        spacing = 40

        for node in self.nodes.values():
            node.step.pos_x = x
            node.step.pos_y = y

            self.coords(node.rect_id, x, y, x + node.width, y + node.height)
            self.coords(node.text_id, x + node.width / 2, y + node.height / 2)

            x += node_width + spacing
            if x + node_width > canvas_width:
                x = 50
                y += node.height + spacing
        
        self.update_scroll_region()

    def draw_all_connections(self):
        """Draw all connections between nodes based on step dependencies."""
        # Clear existing connections
        for conn in self.connections:
            self.delete(conn)
        self.connections = []
        
        # Draw new connections
        for step in self.app.current_workflow.steps:
            if step.id not in self.nodes: 
                continue
            for dep_id in step.dependencies:
                if dep_id in self.nodes:
                    self.draw_connection(dep_id, step.id)

    def draw_connection(self, from_id: str, to_id: str):
        from_node = self.nodes[from_id]
        to_node = self.nodes[to_id]
        colors = self.app.themes[self.app.current_theme]
        
        line = self.create_line(
            from_node.step.pos_x + from_node.width, from_node.step.pos_y + from_node.height / 2,
            to_node.step.pos_x, to_node.step.pos_y + to_node.height / 2,
            arrow=tk.LAST, fill=colors["conn_color"], width=2, tags=(f"conn-from-{from_id}", f"conn-to-{to_id}")
        )
        self.original_coords[line] = (
            from_node.step.pos_x + from_node.width, from_node.step.pos_y + from_node.height / 2,
            to_node.step.pos_x, to_node.step.pos_y + to_node.height / 2
        )
        self.connections.append(line)
        return line

    def update_connections_for_node(self, step_id: str):
        # Remove connections involving this node
        self.delete(f"conn-from-{step_id}", f"conn-to-{step_id}")
        
        # Remove these connections from our connections list
        connections_to_remove = []
        for conn in self.connections:
            tags = self.gettags(conn)
            if f"conn-from-{step_id}" in tags or f"conn-to-{step_id}" in tags:
                connections_to_remove.append(conn)
        
        for conn in connections_to_remove:
            self.connections.remove(conn)
        
        # Redraw connections for this node
        for step in self.app.current_workflow.steps:
            if step_id in step.dependencies and step.id in self.nodes:
                # This step depends on the moved node
                self.draw_connection(step_id, step.id)
            elif step.id == step_id:
                # This is the moved node, redraw its outgoing connections
                for dep_id in step.dependencies:
                    if dep_id in self.nodes:
                        self.draw_connection(dep_id, step_id)

    def update_node_status(self, step_id: str, status: StepStatus):
        if step_id in self.nodes:
            self.nodes[step_id].update_status(status)

    def select_node(self, step_id: Optional[str], ctrl_pressed: bool = False):
        if not ctrl_pressed:
            # Clear previous selection
            for node_id in self.selected_node_ids:
                if node_id in self.nodes:
                    self.itemconfig(self.nodes[node_id].rect_id, outline=self.app.themes[self.app.current_theme]["node_outline"], width=2)
            self.selected_node_ids.clear()

        if step_id in self.selected_node_ids:
            self.selected_node_ids.remove(step_id)
            self.itemconfig(self.nodes[step_id].rect_id, outline=self.app.themes[self.app.current_theme]["node_outline"], width=2)
        elif step_id:
            self.selected_node_ids.add(step_id)
            self.itemconfig(self.nodes[step_id].rect_id, outline="red", width=3)

        # For single selection compatibility
        if len(self.selected_node_ids) == 1:
            self.selected_node_id = list(self.selected_node_ids)[0]
            self.app.selected_step_id = self.selected_node_id
        else:
            self.selected_node_id = None
            self.app.selected_step_id = None