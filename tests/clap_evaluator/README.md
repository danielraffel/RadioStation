# CLAP Evaluation System

## Problem Statement

The RadioStation app collects audio samples based on themes like "Loud", "Smooth", "Bumpy", and "Soft". To verify these samples match their intended themes, we use CLAP (Contrastive Language-Audio Pre-training) - a model that measures how well audio matches text descriptions.

**The core problem:** Generic prompts like "loud sounds" perform poorly (often <15% accuracy). We need better, more specific prompts that CLAP can understand.

## Solution: AI-Powered Prompt Generation + Systematic Evaluation

This evaluation system solves the problem through:

1. **AI Prompt Generation**: Uses OpenAI to generate specific, descriptive prompts based on YouTube metadata
2. **Systematic Testing**: Evaluates different prompts and thresholds to find optimal configurations
3. **Prompt Management**: Separates experimental prompts from production-ready "blessed" prompts

## System Architecture

```
Audio Sample (WAV) + Metadata (JSON)
         ↓
AI Prompt Generator (OpenAI)
         ↓
3 Descriptive Prompts per Sample
         ↓
CLAP Evaluation Engine
         ↓
Score Results & Analysis
         ↓
Prompt Blessing (Manual Selection)
         ↓
Production Use in RadioStation
```

## Key Components

### 1. Prompt Types

- **Original Prompts**: Generic prompts like "loud sounds" (poor performance)
- **AI-Generated Prompts**: Specific prompts from OpenAI based on YouTube metadata
- **Discovery Prompts**: Auto-generated variations for testing ("loud audio", "loud noise", etc.)
- **Blessed Prompts**: Manually approved high-scoring prompts for production

### 2. Evaluation Modes

#### Full Evaluation
- Tests ALL samples in a session
- Can test multiple configurations simultaneously
- Generates comprehensive HTML report
- Shows pass/fail rates and detailed scores

#### Test This (Single Config)
- Quick test of one configuration
- Faster feedback for iterative testing
- Shows immediate results without full report

#### Discovery Mode
- Tests generic variations of theme names
- Analyzes score distributions
- Recommends optimal thresholds
- Helps understand CLAP's behavior

#### Generate AI Prompts
- Sends YouTube metadata to OpenAI
- Generates 3 descriptive prompts per sample
- Saves to `clap_prompts_v1` field
- Shows real-time progress

## Workflow

### Step 1: Generate AI Prompts
```bash
1. Select a session
2. Click "Generate AI Prompts"
3. Wait for batch processing (shows progress)
4. Prompts saved to sample JSON files
```

**What happens:**
- Extracts title, description, tags from YouTube metadata
- Sends to OpenAI with specific instructions
- Gets back 3 audio-descriptive prompts per sample
- Example: "metallic clang ringing echo sound" instead of "loud"

### Step 2: Run Evaluation
```bash
1. Configure test parameters (threshold, prompts)
2. Click "Run Full Evaluation"
3. View results with audio playback
4. See which prompts performed best
```

**What happens:**
- CLAP scores each audio file against prompts
- Determines if score meets threshold
- Categorizes as pass/fail
- Shows detailed results with actual prompts used

### Step 3: Review & Bless Prompts
```bash
1. Review evaluation results
2. Identify high-scoring prompts
3. Select prompts to bless
4. Click "Bless Selected Prompts"
```

**What happens:**
- High-scoring prompts marked as `final_clap_prompt`
- These become production prompts
- RadioStation uses only blessed prompts
- Evaluation prompts remain for testing

## Data Structure

### Sample JSON Fields

```json
{
  "title": "10 Hours of Thunderstorm Sounds",
  "description": "Relaxing rain and thunder...",
  "tags": ["thunderstorm", "rain", "sleep"],

  // Evaluation prompts (temporary, for testing)
  "clap_prompts_v1": [
    "thunder rumbling with rain",
    "storm sounds with lightning",
    "heavy rainfall and thunder"
  ],
  "best_clap_prompt": "thunder rumbling with rain",

  // Production prompt (blessed, final)
  "final_clap_prompt": "thunder rumbling with rain",
  "final_clap_score": 0.72
}
```

## Configuration

### Settings (`evaluator_config.json`)

```json
{
  "ai_enabled": true,
  "openai_api_key": "sk-...",
  "model": "gpt-4o-mini",
  "batch_size": 10,
  "temperature": 0.7,
  "use_tags": true,
  "use_description": true
}
```

### Thresholds

- **0.3**: Lenient - catches most relevant audio
- **0.4**: Balanced - good precision/recall trade-off
- **0.5**: Strict - high precision, may miss some samples

## Running the Evaluator

```bash
# Start the web interface
cd tests/clap_evaluator
python sessions_browser.py

# Open browser
http://localhost:8001
```

## Understanding Results

### Pass Rate
Percentage of samples that scored above threshold for their intended theme.

### Cross-Assignment
When a sample scores higher for a different theme than intended.

### Score Distribution
- Shows mean, median, min, max scores
- Helps identify optimal thresholds
- Reveals prompt effectiveness

## Feature Explanations

### "Test This" Button
- Tests a single configuration quickly
- Useful for iterating on prompts
- Shows immediate pass/fail feedback
- Doesn't generate full report

### "Run Full Evaluation"
- Tests all configured prompts
- Generates complete HTML report
- Allows comparison between configs
- Best for final validation

### "Discovery Mode"
- **Purpose**: Find baseline performance without AI
- **How it works**: Tests variations like "loud sounds", "loud audio", "loud noise"
- **Use case**: Understanding CLAP's behavior before AI optimization
- **Output**: Score distributions and threshold recommendations

### "Generate AI Prompts"
- **Purpose**: Create better prompts using YouTube metadata
- **How it works**: Sends title/description/tags to OpenAI
- **Output**: 3 descriptive prompts per sample
- **Example**: "metallic clang ringing echo" vs "loud"

## Best Practices

1. **Generate AI prompts first** - They perform much better than generic ones
2. **Start with Discovery Mode** - Understand baseline performance
3. **Test multiple thresholds** - Find the sweet spot for your use case
4. **Review before blessing** - Ensure prompts make sense semantically
5. **Keep evaluation separate** - Don't mix test and production prompts

## Troubleshooting

### Low Pass Rates (<20%)
- Prompts may be too generic
- Generate AI prompts with more specific metadata
- Lower threshold temporarily to analyze scores

### AI Prompt Generation Stuck
- Large sessions (300+ samples) take time
- Check batch_size in settings (lower = slower but more reliable)
- Monitor server logs for API errors

### Audio Won't Play
- Check browser console for errors
- Verify WAV files exist in session directory
- Ensure server has read permissions

### "Test This" Not Working
- Check browser console for errors
- Ensure session is selected
- Verify endpoint `/api/evaluate/single` responds

## Future Improvements

- Multiple prompt testing per sample
- A/B testing framework
- Automated blessing based on score thresholds
- Prompt performance analytics
- Integration with RadioStation's main pipeline