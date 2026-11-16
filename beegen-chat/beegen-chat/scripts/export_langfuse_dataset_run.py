import argparse
from beegenerate.loggings.loggers import lf
from langfuse.decorators import langfuse_context, observe
from pprint import pprint
import pandas as pd

def langfuse_run_to_csv(
    dataset_name: str,
    run_id: str,
    output_path: str,
):
    """
    Export langfuse run results as a CSV file. For historical runs.
 
    This function assumes the trace has only one observation for single user chat input
 
    Run with the following command:
    python -m {python_file_name} --dataset_name <dataset_name> --run_name <run_name> --output_path <output_path>
    """
    langfuse_client = langfuse_context.client_instance
    dataset_run = langfuse_client.get_dataset_run(
        dataset_name=dataset_name, dataset_run_name=run_id
    )
    run_items = []
    for run_item in dataset_run.dataset_run_items[:1]:
        try:
            run_item_dict = {
                "id": run_item.id,
                "dataset_item_id": run_item.dataset_item_id,
                "trace_id": run_item.trace_id,
                "created_at": run_item.created_at,
                "updated_at": run_item.updated_at,
            }
    
            trace = langfuse_client.get_trace(id=run_item.trace_id)
            dataset = langfuse_client.get_dataset("")
            pprint(run_item.id)
            pprint(langfuse_client.get_dataset_item(id=run_item.id))
            # We assume that the trace has only one observation for single user chat input
            # Example - Get fields from json input
            run_item_dict["input"] = trace.input['kwargs']['messages'][0]['content']
            # run_item_dict["expected_output"] = item.ex
            run_item_dict["output"] = trace.input['kwargs']['messages'][0]['content']
            run_item_dict['score'] = trace.scores[0].value
            run_items.append(run_item_dict)
        except Exception as e:
            print(f"ERROR: {e} at {run_item.trace_id}")
    
    df = pd.DataFrame(run_items)
    df.to_csv(output_path, index=False)
 
 
if __name__ == "__main__":
    # args = argparse.ArgumentParser()
    # args.add_argument("--dataset_name", type=str, required=True)
    # args.add_argument("--run_name", type=str, required=True)
    # args.add_argument("--output_path", type=str, required=True)
    # args = args.parse_args()
 
    # langfuse_run_to_csv(args.dataset_name, args.run_name, args.output_path)

    langfuse_run_to_csv("EnterpriseKHCN_TEST", "EnterpriseKHCN_TEST_RUN_2025-08-29 03:33:17.970524", "ktnb_eval.csv")