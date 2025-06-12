#!/usr/bin/env python3

from src.ui.app import create_interface
from src.state_manager import finder # Actual instance from state_manager

# Removed Placeholder for finder, as it's now imported from state_manager

def main():
    print("🔍 Detector de Archivos Duplicados GPU - Refactored Version")
    print("=" * 70)
    # Accessing use_gpu from the finder instance imported from state_manager
    print(f"🚀 Aceleración GPU: {'Disponible' if finder.use_gpu else 'No disponible o error en chequeo inicial'}")

    interface = create_interface() # UI components will access finder via state_manager imports

    # The original script had:
    # from fastapi.staticfiles import StaticFiles
    # interface.app.mount("/static", StaticFiles(directory="."), name="static")
    # This kind of static file mounting, if still necessary, should ideally be handled
    # within the Gradio app setup (perhaps in create_interface or by Gradio itself if it's for custom JS/CSS).
    # For standard Gradio operation, explicit mounting for basic assets is often not needed.

    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False, # Defaulting to False, can be changed via config or command line arg later
        debug=True,  # Useful for development
        show_error=True # Shows detailed errors in the UI
    )

if __name__ == "__main__":
    main()
