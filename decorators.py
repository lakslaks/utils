from datetime import datetime
from functools import lru_cache, wraps
from pydantic import validate_call
from collections import defaultdict
from types import SimpleNamespace
import time

class Decorators:

    @staticmethod
    def validate(func):
        validated_func = validate_call(func)
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return validated_func(*args, **kwargs)
            except Exception as e:
                pairs = [(".".join(str(p) for p in err['loc']), err['type'].split("_")[0])
                         for err in e.errors()]                
                grouped = defaultdict(list)
                for param, typ in pairs:
                    grouped[param].append(typ)
                msgs = [f"arg {param} should be { ' or '.join(types) }" for param, types in grouped.items()]
                print("[VALIDATION ERRORS]\n- " + "\n- ".join(msgs))
                return None
    
        return Decorators._tag(wrapper, "validate")

    @staticmethod
    def retry(times=3, delay=0.01):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                for attempt in range(times):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if attempt == times - 1:
                            raise
                        if delay:
                            time.sleep(delay)
            return Decorators._tag(wrapper, "retry")
        return decorator    

    @staticmethod
    def _get_decorator_stack(func):
        stack = []
        current = func
    
        while hasattr(current, "__wrapped__"):
            name = getattr(current, "__decorator_name__", current.__name__)
            stack.append(name)
            current = current.__wrapped__
    
        # original function
        stack.append(current.__name__)
        return stack

    @staticmethod
    def _tag(wrapper, name):
        wrapper.__decorator_name__ = name
        return wrapper        

    @staticmethod
    def debug(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            show_debug = kwargs.pop('show_debug', True)    
            if show_debug and len(stack:= Decorators._get_decorator_stack(wrapper)) > 1:
                print(f"[DEBUG] Decorator stack: {' -> '.join(stack)}")
    
            print(f"[DEBUG] Calling {func.__name__} with args={args}, kwargs={kwargs}")
    
            start = datetime.now()
            result = func(*args, **kwargs)
    
            if show_debug:
                end = datetime.now()
                delta = (end - start).microseconds
                print(f"[DEBUG] Exec time: {delta}µs.  Returned: {result}")    
            return result
    
        return Decorators._tag (wrapper, "debug")
  
    
    @staticmethod
    def smart_return(func=None):
        def decorator(func):
            @wraps (func)
            def wrapper(*args, **kwargs):
                ret_type = kwargs.pop('exec_detail', None)
                val = func(*args, **kwargs)
                if not isinstance(val, tuple):
                    return val
                if ret_type is None or ret_type == 'resp': # exec_detail not provided → return first element
                    return val[0]
                if isinstance(ret_type, int): # exec_detail = int → return indexed element
                    return val[ret_type]
                if ret_type == 'all': # exec_detail = 'all' → return full tuple
                    return val
                if ret_type == 'detail': # exec_detail = 'detail' → return everything except index 0
                    return val[1:]
                # fallback
                return val
            return Decorators._tag(wrapper, "smart_return")
        if func is not None:
            return decorator(func)
        return decorator

    @staticmethod
    def timeit(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            time_format = kwargs.pop('show_exec_time_format', 'ms')
            return_elapsed = kwargs.pop('return_elapsed', False)
            start = time.perf_counter()
            res = func(*args, **kwargs)
            end = time.perf_counter()
            elapsed = end-start
            elapsed = f"{elapsed * 1000:.3f}ms" if time_format == 'ms' else f"{elapsed:.6f}s"
            if return_elapsed:
                return res, elapsed 
            print (f"{elapsed} -> {func.__name__}")
            return res
        return Decorators._tag (wrapper, "timeit")

    @staticmethod
    def agentic_func(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            agent_mode = kwargs.pop("agent_call", False)
            
            if not agent_mode: # normal execution
                return func(*args, **kwargs)
                
            try: # agent safe execution
                result = func(*args, **kwargs)
                return {"sucess": True, "result": result, "message": None}
            except Exception as e:
                return {"sucess": False, "result": None, "message": str(e)}
        return wrapper
    
    @staticmethod
    def cache(func=None, *, maxsize=128):
        def decorator(func):
            cached = lru_cache(maxsize=maxsize)(func)
    
            @wraps(func)
            def wrapper(*args, **kwargs):
                debug_mode = kwargs.pop("show_debug", False)
                no_cache = debug_mode or kwargs.pop("no_cache", False)
                no_store = kwargs.pop("no_store", False)
       
                if no_cache:
                    return func(*args, **kwargs)
    
                result = cached(*args, **kwargs)    # cached path
                if no_store:
                    cached.cache_clear()
    
                return result
    
            # public cache controls
            wrapper.cache_clear = cached.cache_clear
            wrapper.cache_info = cached.cache_info
        
            return Decorators._tag(wrapper, f"cache({maxsize})")
    
        # support @cache and @cache(...)
        if callable(func):
            return decorator(func)
        return decorator
    
    @staticmethod
    def normalize_exceptions(mapper=None):
        """mapper: optional dict mapping ExceptionType -> normalized message"""
        mapper = mapper or {}

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    exc_type = type(e)
                    msg = mapper.get(exc_type, str(e))
                    return {"error": exc_type.__name__, "message": msg}
            return Decorators._tag(wrapper, "normalize_exceptions")
        return decorator

    @staticmethod
    def hooks(before=None, after=None):
        before = before or (lambda *a, **k: None)
        after  = after  or (lambda *a, **k: None)

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                before(*args, **kwargs)
                result = func(*args, **kwargs)
                after(result, *args, **kwargs)
                return result
            return Decorators._tag(wrapper, "hooks")
        return decorator

    @staticmethod
    def restrict_to_dnu(limit, period):
        def decorator(func):
            limited = sleep_and_retry(limits(calls=limit, period=period)(func))

            @wraps(func)
            def wrapper(*args, **kwargs):
                return limited(*args, **kwargs)

            return Decorators._tag(wrapper, f"rate({limit}/{per}s)")
        return decorator

    @staticmethod
    def log_dnu(logger, level="info"):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                getattr(logger, level)(f"Calling {func.__name__}")
                return func(*args, **kwargs)
            return Decorators._tag(wrapper, f"log({level})")
        return decorator

    @staticmethod
    def wrapcall(*decorators):
        def wrapper(func):
            wrapped = func
            # reverse so user order is left → right
            for deco in reversed(decorators):
                wrapped = deco(wrapped)
            return Decorators._tag(wrapped, "wrapped")
        return wrapper

    @staticmethod
    def sns(func):
        def wrapper(*args, **kwargs):
            result_keys = kwargs.pop('result_keys', 'values')
            result = func(*args, **kwargs)
            _type = type(result)
    
            if result_keys == 'values' or _type not in {list, dict, tuple}:
                return SimpleNamespace(values=result)
            elif _type is dict:
                return SimpleNamespace(**result)
            elif _type in (list, tuple):
                if result_keys == 'auto':
                    return SimpleNamespace(**{f'v{idx}': v for idx, v in enumerate(result, start=1)})
                elif result_keys and len(result_keys) == len(result):
                    if not all(isinstance(i, str) for i in result_keys):
                        raise TypeError("result_keys must all be strings")
                    return SimpleNamespace(**dict(zip(result_keys, result)))
            return SimpleNamespace(values=result)
        return Decorators._tag(wrapper, "sns")
    
if __name__ == '__main__':

    ...