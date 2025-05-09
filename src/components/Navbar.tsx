import React from 'react';
import { Link } from 'react-router-dom';

interface NavbarProps {
  activeItem?: string;
}

const Navbar = ({ activeItem = 'home' }: NavbarProps) => {
  return (
    <header className="fixed top-0 left-0 right-0 bg-white/80 backdrop-blur-md shadow-sm z-50">
      <div className="container mx-auto px-4 md:px-6">
        <nav className="flex items-center justify-between h-16 md:h-20">
          <Link to="/" className="flex items-center gap-2">
            <img 
              src="/lovable-uploads/302cea46-261a-4922-81ac-37e4095b6576.png" 
              alt="ASEND Health Logo" 
              className="h-8 md:h-10" 
            />
            <span className="font-semibold text-lg md:text-xl">ASEND Health</span>
          </Link>
          
          <div className="hidden md:flex items-center space-x-1">
            <Link to="/" className={`nav-link ${activeItem === 'home' ? 'active' : ''}`}>
              Home
            </Link>
            <Link to="/about" className={`nav-link ${activeItem === 'about' ? 'active' : ''}`}>
              About
            </Link>
            <Link to="/services" className={`nav-link ${activeItem === 'services' ? 'active' : ''}`}>
              Services
            </Link>
            <Link to="/contact" className={`nav-link ${activeItem === 'contact' ? 'active' : ''}`}>
              Contact
            </Link>
          </div>
          
          <div className="md:hidden">
            <button className="p-2 rounded-lg hover:bg-gray-100 transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
              </svg>
            </button>
          </div>
        </nav>
      </div>
    </header>
  );
};

export default Navbar;