---
trigger: always_on
---

# Python Docstring & Documentation Guidelines

Always follow the **Google Python Style Guide** for all docstrings in this repository, as configured in `pyproject.toml` and enforced by Ruff (`pydocstyle` convention: `google`, rule set `D`, ignoring `D203` and `D213`).

## 1. Docstring Coverage
- Every public module, class, function, and method must have an informative docstring (`D100`, `D101`, `D102`, `D103`, `D107`).
- Private methods (`_method`) or trivial overrides can be omitted only if self-explanatory, but documenting complex internal logic is encouraged.

## 2. Format & Style Rules
- **Imperative Mood (`D401`)**: The first line (summary) must use the imperative mood (e.g., `"Calculate the loss."`, `"Return token probabilities."`), never descriptive (avoid `"Calculates..."` or `"Function that returns..."`).
- **Punctuation (`D400`)**: The summary line must end with a period (`.`).
- **Summary Structure**:
  - One-line docstrings: `"""Summary line ending with period."""`
  - Multi-line docstrings: Place a blank line between the summary and the detailed description or sections.
- **Quotes**: Always use triple double quotes `"""..."""`.

## 3. Google Style Sections
Follow standard Google-style section headers (`Args:`, `Returns:`, `Yields:`, `Raises:`, `Attributes:`) with 4-space indentation:

```python
def generate_transcription(audio_features: torch.Tensor, max_length: int = 128) -> str:
    """Generate text transcription from input acoustic features.

    Args:
        audio_features (torch.Tensor): Preprocessed mel-spectrogram tensor of shape (batch_size, time_steps, n_mels).
        max_length (int): Maximum sequence length for the output tokens. Defaults to 128.

    Returns:
        str: Decoded transcription string.

    Raises:
        ValueError: If audio_features tensor is empty or has invalid dimensions.
    """
```

## 4. Verification Workflow
Whenever writing or updating Python code:
- Always check docstrings with Ruff using `uv`:
  ```bash
  uv run ruff check --select D <path-to-file>
  ```
- If formatting or autofixable issues exist, apply fixes:
  ```bash
  uv run ruff check --select D --fix <path-to-file>
  ```
- Ensure zero `D` rule violations before finalizing code changes.
