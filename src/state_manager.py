from collections import defaultdict
from src.core.finder import DuplicateFinder

# Initialize the core DuplicateFinder instance
# The use_gpu parameter can be configured here or read from a config file later
finder = DuplicateFinder(use_gpu=True)

# Application state variables
current_results = [] # List to store duplicate group dictionaries
group_selections = defaultdict(lambda: False) # Stores group-level selection states if ever needed
individual_selections = defaultdict(lambda: False) # Stores {file_id: bool} for selection
stop_analysis = False # Boolean flag to signal stopping analysis
