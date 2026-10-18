from functools import wraps


def validate_input_data(serializer_class):
    def decorate(view):
        @wraps(view)
        def validate(self, request, *args, **kwargs):
            serializer = serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            kwargs['validated_data'] = serializer.validated_data

            return view(self, request, *args, **kwargs)

        return validate

    return decorate
