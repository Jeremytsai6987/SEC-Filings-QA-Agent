import streamlit as st
from qa_system import EnhancedSECQASystem

#  Configure the Streamlit page
st.set_page_config(page_title="SEC Q&A System", layout="wide")
st.title("📄 SEC Filings Question Answering System")

st.markdown("""
Ask complex financial research questions using real SEC filings.

The system supports:
- Multi-ticker comparisons
- Trend analysis over time
- Source attribution and key metric extraction

Powered by OpenAI + sec-api.io
""")

#  Initialize the QA system (one instance)
system = EnhancedSECQASystem()

#  Input form
with st.form("qa_form"):
    question = st.text_area(
        "Enter your financial research question:",
        height=150,
        placeholder="e.g. What are the key risk factors for JPMorgan in 2023?"
    )
    submit = st.form_submit_button("Run Analysis")

#  On submit
if submit and question.strip():
    with st.spinner("Analyzing SEC filings..."):
        result = system.answer_question(question)

    #  Display answer
    st.subheader("Answer")
    st.markdown(result.answer)

    #  Metadata
    st.subheader("Metadata")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Confidence Score", f"{result.confidence_score:.2f}")
        st.markdown("**Companies Analyzed:**")
        st.write(", ".join(result.companies_analyzed) or "None")

    with col2:
        st.markdown("**Filing Types Used:**")
        st.write(", ".join(result.filing_types_used) or "None")
        st.markdown("**Time Period:**")
        st.write(result.time_period_covered or "Not specified")

    with col3:
        st.markdown("**Limitations:**")
        if result.limitations:
            for lim in result.limitations:
                st.write(f"- {lim}")
        else:
            st.write("None reported.")

    #  Key metrics
    if result.key_metrics:
        st.subheader("Key Metrics")
        for k, v in result.key_metrics.items():
            st.write(f"**{k}**: {v}")

else:
    st.info("Enter a question above and click 'Run Analysis' to begin.")
