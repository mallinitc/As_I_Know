import streamlit as st

from services.pim_evaluator import evaluate_pim_request


st.set_page_config(
    page_title="Least-Privilege PIM Assistant",
    page_icon="🔐",
    layout="wide"
)


st.title("🔐 Least-Privilege PIM Recommendation Assistant")

st.write(
    "This prototype evaluates Azure PIM role requests from change descriptions "
    "and recommends a least-privilege built-in role."
)


sample_storage_change = """Change Number: CHG12345
Environment: Production
Description:
Need to update firewall and virtual network rules on storage account stgprod001.
This is required to allow the application subnet to access the storage account during deployment.
Requested PIM Role: Contributor
Requested Scope: Subscription
Requested Duration: 8 hours
"""


sample_nsg_change = """Change Number: CHG12346
Environment: Production
Description:
Need to update inbound security rule on network security group nsg-prod-app01.
The rule will allow application traffic from the approved subnet during deployment.
Requested PIM Role: Contributor
Requested Scope: Subscription
Requested Duration: 6 hours
"""


sample_option = st.selectbox(
    "Load sample scenario",
    [
        "Storage networking change",
        "NSG rule change",
        "Blank"
    ]
)

if sample_option == "Storage networking change":
    default_text = sample_storage_change
elif sample_option == "NSG rule change":
    default_text = sample_nsg_change
else:
    default_text = ""


change_text = st.text_area(
    "Paste change description",
    value=default_text,
    height=260
)


model = st.selectbox(
    "Local LLM model",
    [
        "qwen2.5:1.5b-instruct",
        "qwen2.5:7b-instruct"
    ],
    index=0
)


if st.button("Evaluate PIM Request", type="primary"):
    if not change_text.strip():
        st.warning("Please enter a change description.")
    else:
        with st.spinner("Evaluating PIM request..."):
            result = evaluate_pim_request(
                change_text=change_text,
                model=model,
                timeout_seconds=180
            )

        decision = result["final_decision"]

        if decision == "REJECT_OVERPRIVILEGED":
            st.error(f"Decision: {decision}")
        elif decision == "APPROVE_RECOMMENDED":
            st.success(f"Decision: {decision}")
        else:
            st.warning(f"Decision: {decision}")

        st.write(result["reason"])

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Extracted Change Details")
            extracted = result["extracted"]

            st.write("**Change number:**", extracted.get("change_number"))
            st.write("**Environment:**", extracted.get("environment"))
            st.write("**Intent summary:**", extracted.get("intent_summary"))
            st.write("**Resource names:**", extracted.get("resource_names"))
            st.write("**Requested role:**", extracted.get("requested_role"))
            st.write("**Requested scope:**", extracted.get("requested_scope"))
            st.write("**Requested duration:**", extracted.get("requested_duration"))
            st.write("**Extraction confidence:**", result.get("extraction_confidence"))

        with col2:
            st.subheader("Least-Privilege Recommendation")

            st.write("**Matched pattern:**", result.get("matched_pattern"))
            st.write("**Recommended role:**", result.get("recommended_role"))
            st.write("**Recommendation status:**", result.get("recommendation_status"))
            st.write("**LLM model:**", result.get("llm_model"))
            st.write("**LLM elapsed seconds:**", result.get("llm_elapsed_seconds"))

        st.subheader("Required Azure Actions")
        st.code("\n".join(result.get("required_actions", [])))

        st.subheader("Matching Built-in Roles")
        matching_roles = result.get("matching_roles", [])

        if matching_roles:
            st.table([
                {
                    "Role": item["role_name"],
                    "Preference Score": item["preference_score"]
                }
                for item in matching_roles
            ])
        else:
            st.info("No matching roles found.")
