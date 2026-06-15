"""
Configuration module for the Monetary Inflation Dashboard.
Loads API keys and settings from environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration settings for the dashboard."""
    
    # API Keys
    FRED_API_KEY = os.getenv('FRED_KEY')
    BEA_API_KEY = os.getenv('BEA_KEY')
    
    # Data directory
    CACHE_DIR = Path(os.getenv('CACHE_DIR', 'data'))
    
    # Ensure cache directory exists
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # FRED series codes we'll need
    FRED_SERIES = {
        'M2': 'M2SL',  # M2 Money Stock
        'PCE': 'PCE',  # Personal Consumption Expenditures
        'GPDI': 'GPDI',  # Gross Private Domestic Investment
        'GCE': 'GCE',   # Government Consumption Expenditures
        'NETEXP': 'NETEXP',  # Net Exports
        'GDP': 'GDP'    # Gross Domestic Product (for validation)
    }
    
    # BEA settings
    BEA_DATASET = 'nipa'
    BEA_FREQUENCY = 'Q'  # quarterly
    BEA_YEAR = 'all'
    
    @classmethod
    def validate_keys(cls):
        """Validate that required API keys are present."""
        missing = []
        
        if not cls.FRED_API_KEY:
            missing.append('FRED_KEY')
        if not cls.BEA_API_KEY:
            missing.append('BEA_KEY')
            
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return True
    
    @classmethod
    def get_cache_path(cls, filename):
        """Get full path for a cache file."""
        return cls.CACHE_DIR / filename

# Keys are validated lazily in DataSource.__init__ to avoid raising at import time.