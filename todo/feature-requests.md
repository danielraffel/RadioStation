# Feature Requests

## Support for up to 256 Themes

**Current Limitation:** The system is currently hardcoded to support exactly 16 themes maximum.

**Requested Enhancement:** Allow users to configure anywhere from 1 to 256 themes.

### Changes Required:

#### Backend (Python)
- **config.py**:
  - Remove the `[:16]` slicing in `load_themes()` (line 166) and `save_themes()` (line 187)
  - Change the range in line 172 from `range(1, 17)` to use NUM_BANKS dynamically
  - Migrate away from individual THEME1-THEME16 env variables to use themes.json exclusively

#### Frontend (HTML/JavaScript)
- **index.html**:
  - Lines 469 & 764: Change hardcoded `for (let i = 0; i < 16; i++)` loops to use NUM_BANKS from config
  - Add UI pagination or collapsible sections to handle large numbers of themes elegantly
  - The theme rendering already uses `currentThemes.forEach()` so it's partially ready

#### Configuration
- Deprecate THEME1-THEME16 env variables in favor of themes.json
- Update NUM_BANKS validation to allow values up to 256
- Update .env.example to reflect the new approach

### Performance Considerations:
- **UI**: Need pagination or accordion-style collapsible sections for 256 theme inputs
- **Pipeline**: Processing remains sequential by theme, minimal performance impact
- **CLAP scoring**: Would score against up to 256 prompts (slower but feasible)
- **Memory**: Minimal impact, just storing more theme configurations

### Implementation Priority: Low
The current 16-theme limit is sufficient for most use cases. This enhancement would benefit power users who need extensive sample organization.

---

*Add new feature requests below this line*