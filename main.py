#!/usr/bin/env python3
"""
Main entry point for the Bug Bounty Workflow Generator application.
"""

import sys
import os

# Add the project root to the Python path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import WorkflowApp


def main():
    """Main entry point"""
    app = WorkflowApp()
    app.run()


if __name__ == "__main__":
    main()