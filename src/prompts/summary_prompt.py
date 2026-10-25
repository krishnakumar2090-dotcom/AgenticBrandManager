def render_summary_prompt(
    question: str, table_text: str, truncated_note: str, rules_section: str
) -> str:
    """
    Render the results-summarization prompt template.

    Params:
        question: the user's original question.
        table_text: the SQL result preview as CSV text.
        truncated_note: note about row truncation, or an
            empty string if the full result is shown.
        rules_section: formatted response formatting/tone
            rules, or an empty string if none apply.
    """

    return f"""
You are a Business Analyst summarizing SQL query results
for a business user.

Question:
{question}

Query result (CSV):
{table_text}{truncated_note}

Write a short, direct answer to the question using only
the data above, in the same order as the rows are given.
Reference specific values, names, or numbers from the
result. Do not mention SQL, tables, or columns. Do not add
extra commentary beyond answering the question.

{rules_section if rules_section else ""}
"""
