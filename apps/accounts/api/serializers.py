from rest_framework import serializers


class LoginRequestSerializer(serializers.Serializer):
    login = serializers.CharField()
    password = serializers.CharField()


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()
