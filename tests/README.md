# RadioStation Test Suite

## CLAP Evaluator (`/tests/clap_evaluator/`)

### The Problem
RadioStation collects audio samples for themes like "Loud", "Smooth", "Bumpy", and "Soft". We use CLAP (Contrastive Language-Audio Pre-training) to verify samples match their themes, but generic prompts like "loud sounds" perform terribly (~15% accuracy).

### The Solution
**AI-powered prompt generation + systematic evaluation**

1. **Generate better prompts**: Use OpenAI to create specific descriptions from YouTube metadata
2. **Test systematically**: Evaluate different prompts and thresholds
3. **Bless the best**: Mark high-scoring prompts for production use

### Quick Workflow

```bash
# 1. Start the evaluator
cd tests/clap_evaluator
python sessions_browser.py
# Open http://localhost:8001

# 2. Generate AI prompts (uses YouTube metadata → OpenAI → 3 prompts/sample)
Click "Generate AI Prompts"

# 3. Run evaluation
Click "Run Full Evaluation"

# 4. Review results & bless good prompts
Review scores → Select high performers → "Bless Selected Prompts"
```

### Key Features Explained

#### "Test This" Button
- **What**: Quick test of single configuration
- **Use**: Fast iteration on prompts without full evaluation
- **Output**: Immediate pass/fail rates in a modal

#### "Run Full Evaluation"
- **What**: Complete test of all samples
- **Use**: Final validation with comprehensive report
- **Output**: HTML report with audio playback, scores, and detailed results

#### "Discovery Mode"
- **What**: Tests generic variations ("loud sounds", "loud audio", "loud noise")
- **Use**: Baseline performance without AI
- **Output**: Score distributions and threshold recommendations
- **Prompts from**: Hardcoded variations of theme names

#### "Generate AI Prompts"
- **What**: Creates descriptive prompts using OpenAI
- **Use**: Get better prompts than generic ones
- **Example**: "metallic clang ringing echo" vs "loud"

#### "View AI Prompts" (appears after generation)
- **What**: Shows all generated prompts with metadata
- **Use**: Review what OpenAI created before testing

### Data Structure

```json
{
  // YouTube metadata
  "title": "10 Hours Thunder & Rain",
  "tags": ["thunderstorm", "rain"],

  // AI evaluation prompts (3 per sample)
  "clap_prompts_v1": [
    "thunder rumbling with rain",
    "storm sounds with lightning",
    "heavy rainfall and thunder"
  ],

  // Production prompt (manually blessed)
  "final_clap_prompt": "thunder rumbling with rain",
  "final_clap_score": 0.72
}
```

### Understanding Results

- **Pass Rate**: % of samples scoring above threshold for correct theme
- **Cross-Assignment**: Samples scoring higher for wrong theme
- **Blessed vs Evaluation**:
  - Evaluation prompts = testing/experimentation
  - Blessed prompts = approved for RadioStation production

### Files

- `evaluator.py` - Core CLAP scoring engine
- `sessions_browser.py` - Web UI server
- `clap_prompt_generator.py` - OpenAI integration
- `prompt_manager.py` - Blessing/production prompt management
- `report_generator.py` - Enhanced HTML reports
- `evaluator_config.json` - AI settings

For detailed documentation, see `/tests/clap_evaluator/README.md`