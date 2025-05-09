import React from 'react';
import Navbar from '@/components/Navbar';
import LoginForm from '@/components/LoginForm';

const Login = () => {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      
      <div className="flex-1 bg-gradient-to-br from-[#E0F7FA] to-[#E0F2F1] pt-16">
        <div className="container mx-auto px-4 md:px-6 py-12 md:py-20 min-h-[calc(100vh-4rem)]">
          <div className="flex flex-col md:flex-row h-full">
            {/* Left side - Login Form */}
            <div className="w-full md:w-1/2 flex items-center justify-center p-4 md:p-8">
              <LoginForm />
            </div>
            
            {/* Right side - Background Image */}
            <div className="hidden md:block w-1/2 bg-mountains rounded-2xl shadow-lg overflow-hidden">
              <div className="h-full login-gradient flex flex-col items-center justify-center text-center p-8">
                <h2 className="text-3xl font-bold mb-4 text-gray-800">Your Health Journey Starts Here</h2>
                <p className="text-lg text-gray-700 mb-6">Access personalized care and resources to help you reach new heights in your wellbeing.</p>
                <div className="w-24 h-1 bg-primary rounded-full mb-8"></div>
                <div className="grid grid-cols-2 gap-4 max-w-sm">
                  <div className="bg-white/80 backdrop-blur-sm p-4 rounded-lg shadow-sm">
                    <div className="text-primary text-xl font-semibold mb-1">24/7</div>
                    <div className="text-sm text-gray-600">Access to care</div>
                  </div>
                  <div className="bg-white/80 backdrop-blur-sm p-4 rounded-lg shadow-sm">
                    <div className="text-primary text-xl font-semibold mb-1">100%</div>
                    <div className="text-sm text-gray-600">Personalized</div>
                  </div>
                  <div className="bg-white/80 backdrop-blur-sm p-4 rounded-lg shadow-sm">
                    <div className="text-primary text-xl font-semibold mb-1">500+</div>
                    <div className="text-sm text-gray-600">Specialists</div>
                  </div>
                  <div className="bg-white/80 backdrop-blur-sm p-4 rounded-lg shadow-sm">
                    <div className="text-primary text-xl font-semibold mb-1">50k+</div>
                    <div className="text-sm text-gray-600">Happy patients</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <footer className="bg-white border-t py-4">
        <div className="container mx-auto px-4 text-center text-sm text-gray-500">
          &copy; 2023 ASEND Health. All rights reserved.
          <div className="mt-1">
            <a href="#" className="text-primary hover:underline mx-2">Privacy Policy</a>
            <a href="#" className="text-primary hover:underline mx-2">Terms of Service</a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Login;