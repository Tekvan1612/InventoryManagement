from django.shortcuts import redirect
from django.urls import reverse


class SessionAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if the user is logged in by looking for 'username' in the session
        if not request.session.get('username') and request.path != reverse('login_view'):
            return redirect(reverse('login_view'))

        response = self.get_response(request)
        return response

