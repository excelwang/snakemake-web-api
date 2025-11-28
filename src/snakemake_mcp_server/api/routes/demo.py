from fastapi import APIRouter, Request
from ...schemas import DemoCaseResponse, UserWrapperRequest

router = APIRouter()

@router.get("/demo-case", response_model=DemoCaseResponse, operation_id="get_snpsift_vartype_demo_case")
async def get_snpsift_vartype_demo_case(request: Request):
    """
    Provides a demo case for running the 'bio/snpsift/varType' wrapper via the /tool-processes endpoint,
    including the request payload and a curl example.
    
    The /tool-processes endpoint will be responsible for creating any necessary dummy input files.
    """
    # Define input and output file names relative to the workdir
    input_file_name = "in.vcf"
    output_file_name = "annotated/out.vcf"

    # Construct the UserSnakemakeWrapperRequest payload
    user_payload = UserWrapperRequest(
        wrapper_id="bio/snpsift/varType",
        inputs={"vcf": input_file_name}, # Relative to workdir
        outputs={"vcf": output_file_name}, # Relative to workdir
    )

    # Construct the DemoCaseResponse
    demo_case = DemoCaseResponse(
        method="POST",
        endpoint="/tool-processes",
        payload=user_payload,
        curl_example="" # Will be filled below
    )

    # Generate curl example using the user_payload and dynamic base URL
    payload_json = user_payload.model_dump_json(indent=2)
    base_url_str = str(request.base_url).rstrip('/') # Ensure no trailing slash
    curl_example = f"""curl -X POST \"{base_url_str}/tool-processes\" \
     -H \"Content-Type: application/json\" \
     -d '{payload_json}'"""
    
    demo_case.curl_example = curl_example
    
    return demo_case
