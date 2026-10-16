#filename: response_contract.py

from functools import wraps

EXPECTED_TYPES = {
    "success": bool,
    "answer": str,
    "sources": list,
    "metadata": dict,
}
EXPECTED_KEYS = set(EXPECTED_TYPES)


def enforce_response_contract(agent_name):
    def decorator(agent_function):
        @wraps(agent_function)
        def wrapper(*args, **kwargs):
            response = agent_function(*args, **kwargs)

            if not isinstance(response, dict):
                raise TypeError(
                    f"{agent_name} must return a dict; "
                    f"got {type(response).__name__}"
                )

            actual_keys = set(response)
            if actual_keys != EXPECTED_KEYS:
                raise ValueError(
                    f"{agent_name} response keys mismatch: "
                    f"missing={sorted(EXPECTED_KEYS - actual_keys)}, "
                    f"extra={sorted(actual_keys - EXPECTED_KEYS)}"
                )

            for key, expected_type in EXPECTED_TYPES.items():
                if type(response[key]) is not expected_type:
                    raise TypeError(
                        f"{agent_name}.{key} must be {expected_type.__name__}; "
                        f"got {type(response[key]).__name__}"
                    )

            return response

        return wrapper
    return decorator